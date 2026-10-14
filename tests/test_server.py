"""End-to-end smoke test: the real server driving a fake `claude` in a PTY.

Covers the platform-specific parts (pseudo-terminal, window size, process
exit) plus the WebSocket protocol, without Claude Code or tokens.
"""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parent.parent
FAKE = Path(__file__).resolve().parent / "fake_claude.py"


def screen_text(frame):
    rows = []
    for line in frame["lines"]:
        runs = line.get("g", []) + line["r"]
        rows.append("".join(r[0] for r in runs).rstrip())
    return "\n".join(rows)


async def run_session():
    os.chmod(FAKE, 0o755)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "typesetter.server", "--no-browser", "--claude", str(FAKE),
        cwd=ROOT, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": str(ROOT)})
    line = (await asyncio.wait_for(proc.stderr.readline(), 15)).decode()
    host, token = re.search(r"http://([^/]+)/\?token=(\S+)", line).groups()
    frames = []

    async def until(pred, what):
        async def wait():
            while True:
                msg = await ws.receive()
                if msg.type != aiohttp.WSMsgType.TEXT:
                    raise AssertionError(f"socket closed waiting for {what}")
                data = json.loads(msg.data)
                if data["t"] == "frame":
                    frames.append(data)
                if pred(data):
                    return data
        return await asyncio.wait_for(wait(), 15)

    async with aiohttp.ClientSession() as http:
        async with http.ws_connect(f"ws://{host}/ws?token={token}",
                                   headers={"Origin": f"http://{host}"}) as ws:
            await ws.send_json({"t": "resize", "cols": 90, "rows": 30})
            frame = await until(lambda d: d["t"] == "frame" and "Hello" in screen_text(d),
                                "the first screen")
            await ws.send_json({"t": "key", "key": "x"})
            await until(lambda d: d["t"] == "frame" and "got b'x'" in screen_text(d), "echo")
            await ws.send_json({"t": "key", "key": "Enter"})
            await until(lambda d: d["t"] == "frame" and "got b'\\r'" in screen_text(d), "Enter")
            await ws.send_json({"t": "key", "key": "q"})
            exited = await until(lambda d: d["t"] == "exit", "exit")
    stdout, _ = await asyncio.wait_for(proc.communicate(), 15)
    return frame, exited, proc.returncode, stdout.decode()


def test_server_with_fake_claude():
    frame, exited, code, stdout = asyncio.run(run_session())
    text = screen_text(frame)
    assert "size 90x30" in text  # the PTY got the browser's size
    hello = next(l for l in frame["lines"] if "Hello" in "".join(r[0] for r in l["r"]))
    assert hello["k"] == "p"  # classified as prose end to end
    assert exited["code"] == 0 and code == 0
    # What claude prints on leaving the alternate screen reaches the terminal,
    # without its escape sequences (stdout isn't a TTY here).
    assert stdout == ("Resume this session with:\nclaude --resume 1234-abcd\n"
                      "Or in typeset-claude:\ntypeset-claude --resume 1234-abcd\n")


def test_unauthorised_websocket_rejected():
    async def attempt():
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "typesetter.server", "--no-browser", "--claude", str(FAKE),
            cwd=ROOT, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": str(ROOT)})
        try:
            line = (await asyncio.wait_for(proc.stderr.readline(), 15)).decode()
            host, token = re.search(r"http://([^/]+)/\?token=(\S+)", line).groups()
            async with aiohttp.ClientSession() as http:
                for url, origin in ((f"ws://{host}/ws?token=wrong", f"http://{host}"),
                                    (f"ws://{host}/ws?token={token}", "http://evil.example")):
                    try:
                        async with http.ws_connect(url, headers={"Origin": origin}):
                            return False
                    except aiohttp.WSServerHandshakeError as e:
                        assert e.status == 403
            return True
        finally:
            proc.terminate()
            await proc.wait()
    assert asyncio.run(attempt())


# --- Claude Code 2.1.299 (starting point; expected to fail until implemented) ---


def test_short_resume_command_at_exit(capsys):
    # 2.1.299: "Changed the resume command printed at exit of a worktree session:
    # it uses -w and -r if the long flags do not fit the terminal"
    # (exact output shape assumed: "claude -w -r <session id>")
    from types import SimpleNamespace
    from typesetter.server import print_exit_text

    session = SimpleNamespace(exit_text=lambda color: "Resume this session with:\nclaude -w -r 1234abcd")
    print_exit_text(session)
    assert "typeset-claude --resume 1234abcd" in capsys.readouterr().out
