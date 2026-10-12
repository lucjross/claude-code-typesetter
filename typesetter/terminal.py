"""pyte-based terminal emulator, patched for what Claude Code sends.

pyte 0.8.2 gaps this fills:
  * SU / SD (CSI n S / CSI n T, scroll the region up / down) are not
    implemented. Claude Code scrolls the conversation with a scroll region
    plus SU, so without them old rows stay put and new text overwrites them.
  * CSI sequences with a "<", "=" or ">" prefix (keyboard protocol and
    version queries such as CSI > 4 ; 2 m) are misparsed: CSI > 4;2 m turns
    on underline, and CSI < u leaks "u" onto the screen. They only configure
    or query the terminal, so they are dropped before pyte sees them.
"""
import re

import pyte
from pyte.screens import Margins

PRIVATE_CSI = re.compile(rb"\x1b\[[<=>][0-9;:]*[ -/]*[@-~]")
# An escape sequence cut off at the end of a read.
PARTIAL_ESC = re.compile(rb"\x1b(?:\[[<=>?]?[0-9;:]*[ -/]*)?$")


class Screen(pyte.Screen):
    def __init__(self, cols, rows, reply=None):
        super().__init__(cols, rows)
        self._reply = reply

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
        super().feed(PRIVATE_CSI.sub(b"", data))
