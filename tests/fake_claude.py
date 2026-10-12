#!/usr/bin/env python3
"""Stand-in for `claude` in tests/test_server.py: no network, no tokens.

Prints its terminal size and an assistant-style line, then echoes each
input byte it reads until it gets "q". Then, like claude, it leaves the
alternate screen and prints a resume hint.
"""
import os
import sys
import tty

fd = sys.stdin.fileno()
tty.setraw(fd)
cols, rows = os.get_terminal_size(fd)
out = (
    "\x1b[?1049h\x1b[H\x1b[2J"
    f"size {cols}x{rows}\r\n"
    "\x1b[38;2;255;255;255m●\x1b[39m Hello from the fake claude, a line of prose.\r\n"
)
os.write(1, out.encode())
while True:
    ch = os.read(fd, 1)
    if not ch or ch == b"q":
        break
    os.write(1, f"got {ch!r}\r\n".encode())
os.write(1, b"\x1b[?1049l\x1b[>4m\x1b(B\x0f\x1b[?25h\x1b7\x1b[r\x1b8\x1b]0;\x07"
            b"\x1b[2m\x1b[22m\r\n\x1b[2mResume this session with:\x1b[22m\r\n"
            b"\x1b[2mclaude --resume 1234-abcd\x1b[22m\r\n\x1b[2m\x1b[22m\x1b[?25h")
