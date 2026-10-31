"""Markdown tables drawn as a box-drawing grid become HTML tables.

The layout and colours follow a real Claude Code 2.1.316 capture: the top
border shares its row with the "●" bullet, the header is centred and not
bold, and cells keep bold and inline-code colours.
"""
from typesetter.classify import classify
from typesetter.server import Session
from typesetter.terminal import Screen, Stream

from test_classify import synthetic

CODE = "\x1b[38;2;177;185;249m{}\x1b[39m"
TABLE = [
    "● ┌──────────────┬──────────────────────┐",
    "  │     Part     │  What it depends on  │",
    "  ├──────────────┼──────────────────────┤",
    "  │ Browser      │ A Chrome extension   │",
    "  │ automation   │ or the \x1b[1mdesktop\x1b[22m app   │",
    "  ├──────────────┼──────────────────────┤",
    "  │ MCP servers  │ " + CODE.format("npx") + " or uvx, Connect- │",
    "  │              │ compatible           │",
    "  └──────────────┴──────────────────────┘",
]


def test_grid_is_a_table():
    info = classify(synthetic(TABLE, 60), 60)
    assert info[0] == {"kind": "table", "gutter": 2, "spans": [[3, 17], [18, 40]],
                       "rows": [[1], [3, 4], [6, 7]]}
    assert all(i == {"kind": "table", "part": True} for i in info[1:])


def test_partial_or_irregular_grids_stay_mono():
    # Bottom border not on screen yet (streaming, or scrolled).
    info = classify(synthetic(TABLE[:-1], 60), 60)
    assert {i["kind"] for i in info} == {"mono"}
    # Top border scrolled off.
    info = classify(synthetic(TABLE[1:], 60), 60)
    assert {i["kind"] for i in info} == {"mono"}
    # A "│" that doesn't line up with the top border's columns.
    bad = TABLE[:3] + ["  │ Browser    │ A Chrome extension     │"] + TABLE[-1:]
    assert {i["kind"] for i in classify(synthetic(bad, 60), 60)} == {"mono"}
    # A grid drawn in code colours (inside a fenced code block).
    code = [TABLE[0][:2] + CODE.format(TABLE[0][2:])] + [
        "  " + CODE.format(r[2:]) for r in TABLE[1:]]
    assert {i["kind"] for i in classify(synthetic(code, 60), 60)} == {"mono"}


def text(cell):
    return "".join(run[0] for run in cell)


def test_frame_sends_cells():
    s = Session.__new__(Session)  # frame() only needs the screen
    s.screen = Screen(60, len(TABLE))
    Stream(s.screen).feed("\r\n".join(TABLE).encode())
    s.screen.cursor.hidden = True
    lines = s.frame()["lines"]
    first = lines[0]
    assert first["k"] == "t" and not first["j"]
    assert [[text(c) for c in row] for row in first["t"]] == [
        ["Part", "What it depends on"],
        ["Browser automation", "A Chrome extension or the desktop app"],
        ["MCP servers", "npx or uvx, Connect-compatible"],
    ]
    # Bold and inline-code colour survive.
    assert ["desktop", "default", "default", 1] in first["t"][1][1]
    assert first["t"][2][1][0][:2] == ["npx", "b1b9f9"]
    assert text(first["g"]) == "● "
    assert all(line == {"k": "t", "j": True, "r": []} for line in lines[1:])
