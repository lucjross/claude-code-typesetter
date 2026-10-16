"""pyte-based terminal emulator, patched for what Claude Code sends.

pyte 0.8.2 gaps this fills:
  * SU / SD (CSI n S / CSI n T, scroll the region up / down) are not
    implemented. Claude Code scrolls the conversation with a scroll region
    plus SU, so without them old rows stay put and new text overwrites them.
  * CSI sequences with a "<", "=" or ">" prefix (keyboard protocol and
    version queries such as CSI > 4 ; 2 m) are misparsed: CSI > 4;2 m turns
    on underline, and CSI < u leaks "u" onto the screen. They only configure
    or query the terminal, so they are dropped before pyte sees them.
  * OSC 8 hyperlinks are ignored. Claude Code uses them for links, so cells
    drawn inside one carry its URL (Char.link).
"""
import re
from typing import NamedTuple, Optional

import pyte
from pyte.screens import Margins

PRIVATE_CSI = re.compile(rb"\x1b\[[<=>][0-9;:]*[ -/]*[@-~]")
# OSC 8 ; params ; URI, ended by BEL or ST. An empty URI ends the link.
HYPERLINK = re.compile(rb"\x1b\]8;[^;\x07\x1b]*;([^\x07\x1b]*)(?:\x07|\x1b\\)")
# An escape sequence cut off at the end of a read (CSI, or OSC before its end).
PARTIAL_ESC = re.compile(rb"\x1b(?:\[[<=>?]?[0-9;:]*[ -/]*|\][^\x07\x1b]*\x1b?)?$")


class Char(NamedTuple):
    """pyte's Char plus the URL of the hyperlink it was drawn in."""
    data: str
    fg: str = "default"
    bg: str = "default"
    bold: bool = False
    italics: bool = False
    underscore: bool = False
    strikethrough: bool = False
    reverse: bool = False
    blink: bool = False
    link: Optional[str] = None


class Screen(pyte.Screen):
    def __init__(self, cols, rows, reply=None):
        super().__init__(cols, rows)
        self._reply = reply

    @property
    def default_char(self):
        return Char(data=" ", reverse=pyte.modes.DECSCNM in self.mode)

    def reset(self):
        super().reset()
        self.cursor.attrs = self.default_char

    def set_link(self, url):
        self.cursor.attrs = self.cursor.attrs._replace(link=url or None)

    def select_graphic_rendition(self, *attrs, **kwargs):
        # SGR 0 resets colours, not the hyperlink the text is in.
        link = self.cursor.attrs.link
        super().select_graphic_rendition(*attrs, **kwargs)
        self.cursor.attrs = self.cursor.attrs._replace(link=link)

    def write_process_input(self, data):
        # Answers to terminal queries (device attributes, cursor position).
        if self._reply:
            self._reply(data.encode())

    def scroll_up(self, count=None, **kwargs):
        """SU: move lines in the scroll region up, blank lines at the bottom."""
        count = max(count or 1, 1)
        top, bottom = self.margins or Margins(0, self.lines - 1)
        for y in range(top, bottom + 1):
            if y + count <= bottom:
                self.buffer[y] = self.buffer[y + count]
            else:
                self.buffer.pop(y, None)
        self.dirty.update(range(top, bottom + 1))

    def scroll_down(self, count=None, **kwargs):
        """SD: move lines in the scroll region down, blank lines at the top."""
        count = max(count or 1, 1)
        top, bottom = self.margins or Margins(0, self.lines - 1)
        for y in range(bottom, top - 1, -1):
            if y - count >= top:
                self.buffer[y] = self.buffer[y - count]
            else:
                self.buffer.pop(y, None)
        self.dirty.update(range(top, bottom + 1))


class Stream(pyte.ByteStream):
    csi = {**pyte.ByteStream.csi, "S": "scroll_up", "T": "scroll_down"}

    def __init__(self, screen):
        super().__init__(screen)
        self._pending = b""

    def feed(self, data):
        data = self._pending + data
        m = PARTIAL_ESC.search(data)
        if m:
            self._pending, data = data[m.start():], data[:m.start()]
        else:
            self._pending = b""
        data = PRIVATE_CSI.sub(b"", data)
        pos = 0
        for m in HYPERLINK.finditer(data):
            super().feed(data[pos:m.start()])
            self.listener.set_link(m.group(1).decode("utf-8", "replace"))
            pos = m.end()
        super().feed(data[pos:])
