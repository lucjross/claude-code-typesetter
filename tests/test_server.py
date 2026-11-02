"""End-to-end smoke test: the real server driving a fake `claude` in a PTY.

Covers the platform-specific parts (pseudo-terminal, window size, process
exit) plus the WebSocket protocol, without Claude Code or tokens.
"""
import asyncio
import json
import os
import re
import signal
import sys
from pathlib import Path
from types import SimpleNamespace

import aiohttp
import pytest

from typesetter.server import child_env, print_exit_text

ROOT = Path(__file__).resolve().parent.parent
FAKE = Path(__file__).resolve().parent / "fake_claude.py"


def screen_text(frame):
    rows = []
    for line in frame["lines"]:
        runs = line.get("g", []) + line["r"]
        rows.append("".join(r[0] for r in runs).rstrip())
    return "\n".join(rows)


async def run_session(opened_log):
    os.chmod(FAKE, 0o755)
    # webbrowser.open runs $BROWSER; this one records the URL it was given.
    browser = opened_log.with_suffix(".sh")
    browser.write_text(f'#!/bin/sh\necho "$1" >> {opened_log}\n')
    browser.chmod(0o755)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "typesetter.server", "--no-browser", "--claude", str(FAKE),
        cwd=ROOT, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": str(ROOT), "BROWSER": f"{browser} %s"})
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
            # Only web links are opened, in the default browser.
            await ws.send_json({"t": "open", "url": "file:///etc/passwd"})
            await ws.send_json({"t": "open", "url": "https://example.com/docs"})
            for _ in range(100):
                if opened_log.exists():
                    break
                await asyncio.sleep(0.05)
            await ws.send_json({"t": "key", "key": "q"})
            exited = await until(lambda d: d["t"] == "exit", "exit")
    stdout, _ = await asyncio.wait_for(proc.communicate(), 15)
    return frame, exited, proc.returncode, stdout.decode()


def test_server_with_fake_claude(tmp_path):
    opened = tmp_path / "opened.txt"
    frame, exited, code, stdout = asyncio.run(run_session(opened))
    text = screen_text(frame)
    assert "size 90x30" in text  # the PTY got the browser's size
    hello = next(l for l in frame["lines"] if "Hello" in "".join(r[0] for r in l["r"]))
    assert hello["k"] == "p"  # classified as prose end to end
    see = next(l for l in frame["lines"] if "the docs" in "".join(r[0] for r in l["r"]))
    assert [r[0] for r in see["r"] if r[4:] == ["https://example.com/docs"]] == ["the docs"]
    assert opened.read_text() == "https://example.com/docs\n"
    assert exited["code"] == 0 and code == 0
    # What claude prints on leaving the alternate screen reaches the terminal,
    # without its escape sequences (stdout isn't a TTY here).
    assert stdout == ("Resume this session with:\nclaude --resume 1234-abcd\n"
                      "Or in typeset-claude:\ntypeset-claude --resume 1234-abcd\n")


def test_ctrl_c_exits_while_a_window_is_open():
    """Ctrl+C in the terminal ends the server promptly, even with a window still connected."""
    async def run():
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "typesetter.server", "--no-browser", "--claude", str(FAKE),
            cwd=ROOT, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": str(ROOT)})
        line = (await asyncio.wait_for(proc.stderr.readline(), 15)).decode()
        host, token = re.search(r"http://([^/]+)/\?token=(\S+)", line).groups()
        seen = []
        async with aiohttp.ClientSession() as http:
            async with http.ws_connect(f"ws://{host}/ws?token={token}",
                                       headers={"Origin": f"http://{host}"}) as ws:
                await ws.send_json({"t": "resize", "cols": 90, "rows": 30})
                while True:  # wait until claude is running
                    msg = await asyncio.wait_for(ws.receive(), 15)
                    if json.loads(msg.data)["t"] == "frame":
                        break
                proc.send_signal(signal.SIGINT)
                try:
                    code = await asyncio.wait_for(proc.wait(), 5)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    return None, seen
                # The window is told claude exited, then the socket is closed.
                while True:
                    msg = await asyncio.wait_for(ws.receive(), 5)
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        break
                    seen.append(json.loads(msg.data)["t"])
        return code, seen
    code, seen = asyncio.run(run())
    assert code is not None, "server kept running while the window was open"
    assert "exit" in seen


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



@pytest.mark.parametrize("command, hint", [
    ('claude --worktree "fix-login" --resume 1234-abcd',
     'typeset-claude --worktree "fix-login" --resume 1234-abcd'),
    # 2.1.299: short flags when the long ones don't fit the terminal
    ('claude -w "fix-login" -r 1234-abcd', 'typeset-claude -w "fix-login" -r 1234-abcd'),
])
def test_exit_hint_for_worktree_resume(capsys, command, hint):
    session = SimpleNamespace(exit_text=lambda color: f"Resume this session with:\n{command}")
    print_exit_text(session)
    assert capsys.readouterr().out.endswith(f"Or in typeset-claude:\n{hint}\n")


def test_claude_keeps_truecolor_inside_tmux(monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1,0")
    env = child_env()
    assert env["CLAUDE_CODE_TMUX_TRUECOLOR"] == "1"
    assert env["TMUX"]  # tools run inside Claude Code can still use tmux
