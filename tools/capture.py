"""Record Claude Code TUI captures for the compatibility tests.

usage: python tools/capture.py OUT_DIR [--claude PATH] [--model MODEL]

Drives the installed `claude` in a pseudo-terminal through fixed scenarios
and writes OUT_DIR/<scenario>.raw (raw terminal output up to the moment of
the snapshot) plus OUT_DIR/manifest.json. tests/test_live.py replays them.

Scenarios that only open UI (trust dialog, startup screen, slash menu,
/model picker) send no prompts. "reply", "permission-dialog" and
"scrolling" send short prompts, on Haiku by default. The permission dialog
is declined, so nothing is run.
"""
import argparse
import fcntl
import json
import os
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from typesetter.classify import _input_box  # noqa: E402
from typesetter.server import CLAUDE_DEFAULT_ARGS  # noqa: E402
from typesetter.terminal import Screen, Stream  # noqa: E402

REPLY_PROMPT = (
    "Without using any tools, reply with: a heading, a two-sentence paragraph "
    "long enough to wrap that contains inline code like `foo()`, a 3-item "
    "bullet list, a fenced python code block of 4 lines, and a final "
    "one-line paragraph."
)
# A read-only command like echo is auto-approved; this one needs approval.
BASH_PROMPT = "Use the Bash tool to run exactly this command: touch typesetter-capture.txt"
SCROLL_PROMPT = (
    "Without using tools, write 40 numbered lines, each a short sentence "
    "like: 7. The seventh line is here."
)

# Session markers inherited when this runs inside Claude Code (e.g. from the
# CI fix agent); passing them on changes the child's behaviour.
KEEP_ENV = {"CLAUDE_CODE_OAUTH_TOKEN"}


class CaptureError(Exception):
    pass


class Session:
    def __init__(self, argv, cwd, cols, rows):
        self.cols, self.rows = cols, rows
        env = {k: v for k, v in os.environ.items()
               if k in KEEP_ENV or not (k.startswith("CLAUDE_CODE_") or k in
                                        ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT"))}
        env.update(TERM="xterm-256color", COLORTERM="truecolor",
                   CLAUDE_CODE_TMUX_TRUECOLOR="1")  # as server.child_env()
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.chdir(cwd)
            os.execvpe(argv[0], argv, env)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.screen = Screen(cols, rows, reply=lambda d: os.write(self.fd, d))
        self.stream = Stream(self.screen)
        self.raw = bytearray()

    def pump(self, secs):
        end = time.time() + secs
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                try:
                    data = os.read(self.fd, 65536)
                except OSError:
                    raise CaptureError("claude exited\n" + self.text())
                if not data:
                    raise CaptureError("claude exited\n" + self.text())
                self.raw.extend(data)
                self.stream.feed(data)

    def text(self):
        return "\n".join(line.rstrip() for line in self.screen.display)

    def rows_now(self):
        return [[self.screen.buffer[y][x] for x in range(self.cols)] for y in range(self.rows)]

    def wait_for(self, pred, what, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            self.pump(0.2)
            if pred():
                return
        raise CaptureError(f"timed out waiting for {what}\n{self.text()}")

    def wait_idle(self, quiet=1.5, timeout=60):
        end = time.time() + timeout
        last, since = len(self.raw), time.time()
        while time.time() < end:
            self.pump(0.2)
            if len(self.raw) != last:
                last, since = len(self.raw), time.time()
            elif time.time() - since >= quiet:
                return

    def ready(self):
        return _input_box(self.rows_now()) is not None

    def busy(self):
        return "esc to interrupt" in self.text()

    def send(self, data, settle=0.3):
        os.write(self.fd, data)
        self.pump(settle)

    def type(self, text):
        for ch in text:
            os.write(self.fd, ch.encode())
            self.pump(0.01)

    def submit(self, prompt):
        self.type(prompt)
        self.pump(0.5)
        self.send(b"\r")

    def wait_reply(self, timeout=120):
        self.wait_for(self.busy, "the reply to start", timeout=30)
        self.wait_for(lambda: not self.busy(), "the reply to finish", timeout=timeout)
        self.wait_idle(2)

    def close(self):
        try:
            os.kill(self.pid, signal.SIGHUP)
            os.waitpid(self.pid, 0)
        except (ProcessLookupError, ChildProcessError):
            pass


def run(out, claude, model):
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"version": subprocess.run([claude, "--version"], capture_output=True,
                                          text=True).stdout.strip(),
                "captures": {}}

    def snapshot(session, name):
        (out / f"{name}.raw").write_bytes(bytes(session.raw))
        manifest["captures"][name] = {"cols": session.cols, "rows": session.rows}
        print(f"captured {name}", file=sys.stderr)

    workdir = Path(tempfile.mkdtemp(prefix="typesetter-capture-"))
    try:
        s = Session([claude, *CLAUDE_DEFAULT_ARGS, "--model", model, "--permission-mode", "default"], workdir, 100, 40)
        try:
            s.wait_for(lambda: "trust" in s.text().lower() or s.ready(), "startup", 60)
            if not s.ready():
                s.wait_idle(1)
                snapshot(s, "trust-dialog")
                s.send(b"\x1b[B")  # "Yes, I trust this folder"
                s.send(b"\r")
            s.wait_for(s.ready, "the input box", 60)
            s.wait_idle(2)
            snapshot(s, "startup")

            s.type("/mo")
            s.wait_for(lambda: "/model" in s.text(), "the slash menu")
            s.wait_idle(1)
            snapshot(s, "slash-menu")
            s.send(b"\x7f\x7f\x7f")
            s.wait_idle(1)

            s.submit("/model")
            s.wait_for(lambda: "Select model" in s.text(), "the model picker")
            s.wait_idle(1)
            snapshot(s, "model-picker")
            s.send(b"\x1b")  # leave the model unchanged
            s.wait_for(s.ready, "the input box after /model")
            s.wait_idle(1)

            s.submit(REPLY_PROMPT)
            s.wait_reply()
            snapshot(s, "reply")

            s.submit(BASH_PROMPT)
            s.wait_for(lambda: "Do you want to proceed" in s.text(), "the permission dialog", 120)
            s.wait_idle(1)
            snapshot(s, "permission-dialog")
            s.send(b"\x1b")  # decline
        finally:
            s.close()

        s = Session([claude, *CLAUDE_DEFAULT_ARGS, "--model", model], workdir, 80, 24)
        try:
            s.wait_for(s.ready, "the input box", 60)
            s.wait_idle(1)
            s.submit(SCROLL_PROMPT)
            s.wait_reply()
            snapshot(s, "scrolling")
        finally:
            s.close()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("out", type=Path)
    p.add_argument("--claude", default=shutil.which("claude") or "claude")
    p.add_argument("--model", default="haiku")
    args = p.parse_args()
    try:
        run(args.out, args.claude, args.model)
    except CaptureError as e:
        print(f"capture failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
