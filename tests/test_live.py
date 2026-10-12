"""Compatibility checks against fresh captures of the installed Claude Code.

Record captures with `python tools/capture.py DIR`, then run
`CAPTURE_DIR=DIR pytest tests/test_live.py`. Without CAPTURE_DIR these are
skipped. Replies differ run to run, so these assert rules (what must be
serif, what must stay monospace) rather than exact text.
"""
import json
import os
import re
from pathlib import Path

import pytest

from typesetter.classify import classify, mask_overlay
from typesetter.terminal import PRIVATE_CSI, Screen, Stream

CAPTURE_DIR = os.environ.get("CAPTURE_DIR")
pytestmark = pytest.mark.skipif(not CAPTURE_DIR, reason="CAPTURE_DIR not set")

# Colours pyte names for the 16 ANSI colours; Claude Code uses these only
# for syntax highlighting.
NAMED = {"black", "red", "green", "brown", "blue", "magenta", "cyan", "white"}
NAMED |= {"bright" + c for c in NAMED}

CSI = re.compile(rb"\x1b\[([?]?)[0-9;:]*([ -/]*)([@-~])")
# Sequences the emulator ignores on purpose (harmless queries).
IGNORED_OK = {"?u"}  # kitty keyboard protocol query


def manifest():
    return json.loads((Path(CAPTURE_DIR) / "manifest.json").read_text())


def capture(name):
    meta = manifest()["captures"].get(name)
    if meta is None:
        pytest.skip(f"no {name} capture")
    raw = (Path(CAPTURE_DIR) / f"{name}.raw").read_bytes()
    screen = Screen(meta["cols"], meta["rows"])
    Stream(screen).feed(raw)
    rows = [[screen.buffer[y][x] for x in range(meta["cols"])] for y in range(meta["rows"])]
    rows, _ = mask_overlay(rows)
    cursor_y = None if screen.cursor.hidden else screen.cursor.y
    info = classify(rows, meta["cols"], cursor_y)
    return rows, info, raw


def text(row):
    return "".join(c.data for c in row).strip()


def find(rows, info, needle):
    for row, i in zip(rows, info):
        if needle in text(row):
            return i
    raise AssertionError(f"{needle!r} not on screen:\n" + "\n".join(text(r) for r in rows))


def test_no_unhandled_escape_sequences():
    handled = set(Stream.csi)
    unhandled = {}
    for path in Path(CAPTURE_DIR).glob("*.raw"):
        data = PRIVATE_CSI.sub(b"", path.read_bytes())
        for m in CSI.finditer(data):
            private, inter, final = (g.decode() for g in m.groups())
            key = private + inter + final
            if inter or final not in handled:
                if key not in IGNORED_OK:
                    unhandled.setdefault(key, set()).add(path.stem)
    assert not unhandled, (
        "Claude Code sends CSI sequences the emulator ignores (typesetter/terminal.py): "
        + ", ".join(f"{k!r} in {sorted(v)}" for k, v in sorted(unhandled.items())))


def test_startup():
    rows, info, _ = capture("startup")
    title = find(rows, info, "Claude Code v")
    assert title["kind"] == "prose" and title.get("fixed")
    assert any(i.get("input") for i in info), "input box not detected"
    mode = find(rows, info, "mode on")
    assert mode["kind"] == "prose"


def test_trust_dialog():
    rows, info, _ = capture("trust-dialog")
    assert any(i["kind"] == "prose" for i in info), "no dialog text detected"
    for row, i in zip(rows, info):
        if text(row).startswith(("/", "~")):
            assert i["kind"] == "mono", text(row)


def test_slash_menu():
    rows, info, _ = capture("slash-menu")
    model = find(rows, info, "/model   ")
    assert model["kind"] == "prose" and model["gutter"] > len("  /model"), \
        "slash menu description not serif"


def test_model_picker():
    rows, info, _ = capture("model-picker")
    assert find(rows, info, "Select model")["kind"] == "prose"


def test_reply():
    rows, info, _ = capture("reply")
    prompt = find(rows, info, "Without using any tools")
    assert prompt["kind"] == "prose" and prompt["bg"] != "default"
    assert sum(i["kind"] == "prose" and not i.get("fixed") for i in info) >= 3, \
        "assistant reply not detected as prose"
    for row, i in zip(rows, info):
        if any(c.fg in NAMED for c in row):  # syntax-highlighted code
            assert i["kind"] == "mono", text(row)


def test_permission_dialog():
    rows, info, _ = capture("permission-dialog")
    assert find(rows, info, "Do you want to proceed")["kind"] == "prose"
    # The command as shown in the dialog (not the submitted prompt or ⎿ line).
    command = [i for row, i in zip(rows, info)
               if text(row).startswith("touch typesetter-capture.txt")]
    assert command and all(i["kind"] == "mono" for i in command)


def test_scrolling_stays_coherent():
    rows, info, _ = capture("scrolling")
    numbers = [int(m.group(1)) for row in rows
               if (m := re.match(r"(?:● )?(\d+)\. ", text(row)))]
    assert numbers, "no numbered lines on screen"
    assert numbers == sorted(set(numbers)), f"lines out of order or repeated: {numbers}"
    assert numbers == list(range(numbers[0], numbers[0] + len(numbers))), numbers
