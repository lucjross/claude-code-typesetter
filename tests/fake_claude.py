#!/usr/bin/env python3
"""Stand-in for `claude` in tests/test_server.py: no network, no tokens.

Prints its terminal size and an assistant-style line, then echoes each
input byte it reads until it gets "q".
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
