"""Run Claude Code in a PTY and serve its screen to a browser window.

The real `claude` TUI runs unmodified; this process emulates the terminal
with pyte, classifies rows (see classify.py), and streams them to the page,
which draws prose rows in a serif face and everything else monospace.
"""
import argparse
import asyncio
import fcntl
import json
import os
import re
import secrets
import shutil
import signal
import struct
import subprocess
import sys
import termios
import webbrowser
from importlib import metadata
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import WSMsgType, web

from .classify import classify, mask_overlay
from .keys import encode
from .terminal import Screen, Stream

STATIC = Path(__file__).parent / "static"
FRAME_DELAY = 0.016
IDLE_EXIT_SECS = 10

# DEC private modes, as pyte stores them (shifted left by 5).
DECCKM = 1 << 5
MOUSE_MODES = {m << 5 for m in (1000, 1002, 1003)}
SGR_MOUSE = 1006 << 5
FOCUS_EVENTS = 1004 << 5
BRACKETED_PASTE = 2004 << 5

FLAG_BOLD, FLAG_ITALIC, FLAG_REVERSE, FLAG_STRIKE = 1, 2, 4, 8

# What claude prints after leaving the alternate screen (e.g. "Resume this
# session with: ...") is meant for the user's terminal, so it's kept and
# printed there on exit.
ALT_SCREEN_ON, ALT_SCREEN_OFF = b"\x1b[?1049h", b"\x1b[?1049l"
MAX_EPILOGUE = 64 * 1024
# Escape sequences other than SGR (colours, dim), plus SI/SO charset shifts.
NON_SGR = re.compile(r"\x1b(?:\[[?<=>][0-9;:]*[ -/]*[@-~]|\[[0-9;:]*[ -/]*[@-ln-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[()][0-9A-Z]|[78=>])|[\x0e\x0f]")
SGR = re.compile(r"\x1b\[[0-9;]*m")
# "claude --resume ID", or for a worktree session 'claude --worktree "NAME"
# --resume ID' ('-w "NAME" -r ID' when that doesn't fit). Group 1 is the args.
RESUME = re.compile(r'\bclaude ((?:(?:--worktree|-w) "[^"]*" (?:--resume|-r)|--resume) \S+)')


def runs(cells):
    """Collapse cells into [text, fg, bg, flags] runs, plus a fifth element,
    the URL, for text inside a hyperlink."""
    out = []
    for c in cells:
        flags = (FLAG_BOLD * c.bold | FLAG_ITALIC * c.italics
                 | FLAG_REVERSE * c.reverse | FLAG_STRIKE * c.strikethrough)
        link = getattr(c, "link", None)
        if (out and out[-1][1] == c.fg and out[-1][2] == c.bg and out[-1][3] == flags
                and (out[-1][4:] or [None])[0] == link):
            out[-1][0] += c.data
        else:
            out.append([c.data, c.fg, c.bg, flags] + ([link] if link else []))
    return out


def openable(url):
    """Only web links are handed to the browser, not file: or other schemes."""
    return isinstance(url, str) and urlsplit(url).scheme in ("http", "https")


def rstrip_runs(rs, bg="default"):
    """Drop trailing spaces drawn on `bg` (the row's own background)."""
    while rs and not rs[-1][0].strip() and rs[-1][2] == bg and not rs[-1][3] & FLAG_REVERSE:
        rs.pop()
    if rs and rs[-1][2] == bg:
        rs[-1][0] = rs[-1][0].rstrip(" ")
    return rs


def cell_runs(rows, ys, a, b):
    """Runs for one table cell: columns [a, b) of screen rows `ys`, each
    line trimmed and joined to the next with a space. A line ending in a
    hyphen ("Connect-") joins the next without one."""
    out = []
    for y in ys:
        rs = rstrip_runs(runs(rows[y][a:b]))
        while rs and not rs[0][0].strip() and rs[0][2] == "default":
            rs.pop(0)
        if rs:
            rs[0][0] = rs[0][0].lstrip(" ")
        if not rs:
            continue
        if out and not re.search(r"\w-$", out[-1][0]):
            out.append([" ", "default", "default", 0])
        out.extend(rs)
    return out


class Session:
    def __init__(self, claude_argv, on_done, keep_alive=False):
        self.claude_argv = claude_argv
        self.on_done = on_done
        # Keep claude running with no window connected (--typeset-remote), so a
        # viewer can come back later, from this machine or another one.
        self.keep_alive = keep_alive
        self.fd = None
        self.proc = None
        self.screen = None
        self.stream = None
        self.clients = set()
        self.frame_pending = False
        self.exit_code = None
        self.idle_task = None
        self.window_closed = False
        self.epilogue = None
        self._carry = b""
        self.loop = asyncio.get_running_loop()
        self.exited = asyncio.Event()

    # -- process ---------------------------------------------------------

    def start(self, cols, rows):
        master, slave = os.openpty()
        self._set_size(master, cols, rows)
        env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor")
        self.proc = subprocess.Popen(
            self.claude_argv, stdin=slave, stdout=slave, stderr=slave,
            env=env, start_new_session=True,
            preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0),
        )
        os.close(slave)
        self.fd = master
        os.set_blocking(master, False)
        self.screen = Screen(cols, rows, self.write)
        self.stream = Stream(self.screen)
        self.loop.add_reader(master, self._on_output)

    @staticmethod
    def _set_size(fd, cols, rows):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def resize(self, cols, rows):
        cols, rows = max(20, int(cols)), max(5, int(rows))
        if self.proc is None:
            self.start(cols, rows)
            return
        if self.exit_code is not None or (cols, rows) == (self.screen.columns, self.screen.lines):
            return
        self.screen.resize(rows, cols)
        self._set_size(self.fd, cols, rows)  # delivers SIGWINCH to claude
        self.schedule_frame()

    def write(self, data):
        if self.fd is not None and self.exit_code is None:
            try:
                os.write(self.fd, data)
            except OSError:
                pass

    def _on_output(self):
        try:
            data = os.read(self.fd, 65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            self._on_exit()
            return
        self._track_epilogue(data)
        self.stream.feed(data)
        self.schedule_frame()

    def _track_epilogue(self, data):
        buf = self._carry + data
        on, off = buf.rfind(ALT_SCREEN_ON), buf.rfind(ALT_SCREEN_OFF)
        if off > on:
            self.epilogue = bytearray(buf[off + len(ALT_SCREEN_OFF):])
        elif on > off:
            self.epilogue = None
        elif self.epilogue is not None:
            self.epilogue += data
            del self.epilogue[:-MAX_EPILOGUE]
        self._carry = buf[-(len(ALT_SCREEN_OFF) - 1):]

    def exit_text(self, color=True):
        """What claude printed after leaving the alternate screen."""
        if not self.epilogue:
            return ""
        text = NON_SGR.sub("", self.epilogue.decode("utf-8", "replace")).replace("\r", "")
        if not color:
            text = SGR.sub("", text)
        lines = text.split("\n")
        while lines and not SGR.sub("", lines[0]).strip():
            lines.pop(0)
        while lines and not SGR.sub("", lines[-1]).strip():
            lines.pop()
        return "\n".join(lines)

    def _on_exit(self):
        self.loop.remove_reader(self.fd)
        self.exit_code = self.proc.wait()
        self.exited.set()
        self.broadcast({"t": "exit", "code": self.exit_code})
        self.loop.call_later(0.5, self.on_done)

    def terminate(self):
        if self.proc and self.exit_code is None:
            try:
                os.killpg(self.proc.pid, signal.SIGHUP)
            except ProcessLookupError:
                pass

    # -- input -----------------------------------------------------------

    def has_mode(self, mode):
        return self.screen is not None and mode in self.screen.mode

    def on_message(self, msg):
        t = msg.get("t")
        if t == "resize":
            self.resize(msg["cols"], msg["rows"])
        elif self.screen is None:
            return
        elif t == "key":
            data = encode(msg["key"], msg.get("ctrl", False), msg.get("alt", False),
                          msg.get("shift", False), self.has_mode(DECCKM))
            if data:
                self.write(data.encode())
        elif t == "paste":
            text = msg["text"].replace("\r\n", "\r").replace("\n", "\r")
            if self.has_mode(BRACKETED_PASTE):
                text = f"\x1b[200~{text}\x1b[201~"
            self.write(text.encode())
        elif t == "wheel":
            if self.has_mode(SGR_MOUSE) and MOUSE_MODES & self.screen.mode:
                button = 64 if msg["dir"] == "up" else 65
                x, y = int(msg.get("x", 0)) + 1, int(msg.get("y", 0)) + 1
                self.write(f"\x1b[<{button};{x};{y}M".encode())
            else:
                key = "ArrowUp" if msg["dir"] == "up" else "ArrowDown"
                self.write(encode(key, app_cursor=self.has_mode(DECCKM)).encode())
        elif t == "focus":
            if self.has_mode(FOCUS_EVENTS):
                self.write(b"\x1b[I" if msg["on"] else b"\x1b[O")
        elif t == "open":
            # A clicked link: open it in the default browser, not the app window.
            if openable(msg.get("url")):
                self.loop.run_in_executor(None, webbrowser.open, msg["url"])

    # -- output ----------------------------------------------------------

    def schedule_frame(self):
        if not self.frame_pending:
            self.frame_pending = True
            self.loop.call_later(FRAME_DELAY, self._send_frame)

    def _send_frame(self):
        self.frame_pending = False
        if self.clients and self.screen is not None:
            self.broadcast(self.frame())

    def frame(self):
        s = self.screen
        cols = s.columns
        screen_rows = [[s.buffer[y][x] for x in range(cols)] for y in range(s.lines)]
        rows, overlay = mask_overlay(screen_rows)
        if overlay:
            # The page draws the pill on top, at the same position.
            y, x0, x1 = overlay["y"], overlay["x0"], overlay["x1"]
            overlay = {"y": y, "x": x0, "r": runs(screen_rows[y][x0:x1])}
        cursor_y = None if s.cursor.hidden else s.cursor.y
        lines = []
        for y, (row, info) in enumerate(zip(rows, classify(rows, cols, cursor_y))):
            if info["kind"] == "prose":
                g, bg = info["gutter"], info.get("bg", "default")
                line = {"k": "p", "j": info["join"], "f": info.get("fixed", False),
                        "a": info.get("right", False), "b": bg, "g": runs(row[:g])}
                if info.get("input"):
                    # Keep typed trailing spaces up to the cursor; "c" is the
                    # cursor's character index within the text.
                    end = max((x + 1 for x in range(g, cols) if (row[x].data or " ").strip()),
                              default=g)
                    if y == cursor_y and s.cursor.x >= g:
                        line["c"] = s.cursor.x - g
                        end = max(end, s.cursor.x)
                    line["i"] = True
                    line["r"] = runs(row[g:end])
                else:
                    line["r"] = rstrip_runs(runs(row[g:]), bg)
                lines.append(line)
            elif info["kind"] == "table":
                if info.get("part"):
                    lines.append({"k": "t", "j": True, "r": []})
                else:
                    lines.append({"k": "t", "j": False, "r": [],
                                  "g": runs(row[:info["gutter"]]),
                                  "t": [[cell_runs(rows, ys, a, b) for a, b in info["spans"]]
                                        for ys in info["rows"]]})
            else:
                lines.append({"k": "m", "r": runs(row)})
        return {"t": "frame", "cols": cols, "rows": s.lines, "lines": lines, "title": s.title,
                "overlay": overlay,
                "cursor": {"x": s.cursor.x, "y": s.cursor.y, "hidden": s.cursor.hidden}}

    def broadcast(self, msg):
        data = json.dumps(msg, separators=(",", ":"))
        for ws in list(self.clients):
            asyncio.ensure_future(ws.send_str(data))

    # -- clients ---------------------------------------------------------

    def attach(self, ws):
        self.clients.add(ws)
        if self.idle_task:
            self.idle_task.cancel()
            self.idle_task = None

    def detach(self, ws):
        self.clients.discard(ws)
        if not self.clients and not self.keep_alive:
            self.idle_task = self.loop.call_later(IDLE_EXIT_SECS, self._idle_exit)

    async def close_clients(self):
        """Close every window's socket (after any queued messages, such as "exit", are sent)."""
        await asyncio.sleep(0)  # let broadcast()'s pending sends go first
        await asyncio.gather(*(ws.close() for ws in list(self.clients)),
                             return_exceptions=True)

    def _idle_exit(self):
        # Window closed and not reopened: end the claude session too. This is
        # a normal way to quit, so it doesn't report claude's SIGHUP status.
        self.window_closed = True
        self.terminate()
        self.loop.call_later(2, self.on_done)


def make_app(session, token, settings):
    async def index(request):
        return web.FileResponse(STATIC / "index.html")

    async def ws_handler(request):
        if request.query.get("token") != token:
            raise web.HTTPForbidden()
        origin = request.headers.get("Origin", "")
        if origin != f"http://{request.host}":
            raise web.HTTPForbidden()
        ws = web.WebSocketResponse(max_msg_size=16 * 1024 * 1024)
        await ws.prepare(request)
        session.attach(ws)
        await ws.send_str(json.dumps({"t": "settings", **settings}))
        if session.screen is not None:
            await ws.send_str(json.dumps(session.frame()))
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    session.on_message(json.loads(msg.data))
        finally:
            session.detach(ws)
        return ws

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static/", STATIC)
    return app


LINUX_BROWSERS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
# Chromium-based macOS apps that support --app windows.
MAC_BROWSERS = ("Google Chrome", "Chromium", "Microsoft Edge", "Brave Browser")


def open_window(url):
    """Open url in a Chromium app window (no tabs or address bar) if possible."""
    if sys.platform == "darwin":
        dirs = (Path("/Applications"), Path.home() / "Applications")
        for app in MAC_BROWSERS:
            if any((d / f"{app}.app").exists() for d in dirs):
                # -n starts a new instance so --app applies even if it's running.
                cmd = ["open", "-na", app, "--args", f"--app={url}"]
                break
        else:
            cmd = None
    else:
        exe = next(filter(None, map(shutil.which, LINUX_BROWSERS)), None)
        cmd = [exe, f"--app={url}"] if exe else None
    if cmd:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    else:
        webbrowser.open(url)


# The rules in classify.py are written for the fullscreen TUI, so use it
# whatever the user's own settings say. A later --settings can override it.
CLAUDE_DEFAULT_ARGS = ["--settings", '{"tui": "fullscreen"}']


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="typeset-claude",
        description="Claude Code with prose in a serif font. "
                    "Unrecognised arguments (and anything after --) go to claude.")
    try:
        version = metadata.version("claude-code-typesetter")
    except metadata.PackageNotFoundError:  # running from a clone
        version = "dev"
    p.add_argument("--version", action="version", version=f"%(prog)s {version}")
    p.add_argument("--port", type=int, default=0, help="HTTP port (default: random)")
    p.add_argument("--no-browser", action="store_true", help="print the URL instead of opening a window")
    p.add_argument("--typeset-remote", action="store_true",
                   help="for use over an SSH tunnel: don't open a window, keep claude running "
                        "while no window is connected, and open clicked links in the viewer's browser")
    p.add_argument("--claude", default="claude", help="claude executable")
    p.add_argument("--serif", default='"Charter", "Bitstream Charter", "Iowan Old Style", Georgia, serif')
    p.add_argument("--mono", default='"JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", monospace')
    p.add_argument("--size", type=float, default=15, help="monospace font size in px")
    p.add_argument("--serif-scale", type=float, default=1.12, help="serif size relative to --size")
    p.add_argument("--option-as-meta", action="store_true",
                   help="macOS: send Option+key as Alt+key instead of typing special characters")
    if "--" in argv:
        i = argv.index("--")
        args, extra = p.parse_known_args(argv[:i])
        extra += argv[i + 1:]
    else:
        args, extra = p.parse_known_args(argv)
    return args, extra


async def main_async(args, claude_args):
    claude = shutil.which(args.claude) or args.claude
    stop = asyncio.Event()
    session = Session([claude, *CLAUDE_DEFAULT_ARGS, *claude_args], stop.set,
                      keep_alive=args.typeset_remote)
    token = secrets.token_urlsafe(18)
    settings = {"serif": args.serif, "mono": args.mono,
                "size": args.size, "serifScale": args.serif_scale,
                "optionAsMeta": args.option_as_meta, "remote": args.typeset_remote}
    runner = web.AppRunner(make_app(session, token, settings))
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", args.port)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    url = f"http://127.0.0.1:{port}/?token={token}"
    print(f"typeset-claude: {url}", file=sys.stderr)
    if not (args.no_browser or args.typeset_remote):
        open_window(url)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await stop.wait()
    finally:
        session.terminate()
        if session.proc is not None:
            try:
                await asyncio.wait_for(session.exited.wait(), 3)
            except asyncio.TimeoutError:
                pass
        # Open windows keep their sockets open, and cleanup() waits for those
        # handlers (up to aiohttp's 60 s shutdown timeout), so close them first.
        await session.close_clients()
        await runner.cleanup()
    print_exit_text(session)
    if session.window_closed:
        return 0
    return session.exit_code or 0


def print_exit_text(session):
    color = sys.stdout.isatty()
    text = session.exit_text(color)
    if not text:
        return
    print(text)
    m = RESUME.search(SGR.sub("", text))
    if m:
        dim, end = ("\x1b[2m", "\x1b[22m") if color else ("", "")
        print(f"{dim}Or in typeset-claude:{end}\n{dim}typeset-claude {m.group(1)}{end}")


def main():
    args, claude_args = parse_args(sys.argv[1:])
    sys.exit(asyncio.run(main_async(args, claude_args)))


if __name__ == "__main__":
    main()
