from pathlib import Path

from typesetter.terminal import Screen, Stream

FIXTURES = Path(__file__).parent / "fixtures"


def replay(data, cols=80, rows=24, chunk=None):
    screen = Screen(cols, rows)
    stream = Stream(screen)
    if chunk:
        for i in range(0, len(data), chunk):
            stream.feed(data[i:i + chunk])
    else:
        stream.feed(data)
    return screen


def test_scroll_region_su():
    # Claude Code scrolls the conversation with DECSTBM + SU (CSI n S).
    screen = replay((FIXTURES / "scrolling-80x24.raw").read_bytes())
    lines = [l.strip() for l in screen.display]
    numbered = [l for l in lines if l[:1].isdigit()]
    assert numbered[0].startswith("24.") and numbered[-1].startswith("40.")
    assert [int(l.split(".")[0]) for l in numbered] == list(range(24, 41))


def test_split_reads_match_single_read():
    data = (FIXTURES / "scrolling-80x24.raw").read_bytes()
    assert replay(data).display == replay(data, chunk=1).display
    assert replay(data).display == replay(data, chunk=7).display


def test_scroll_up_and_down():
    screen = replay(b"a\r\nb\r\nc\r\nd\x1b[2;3r\x1b[1S", cols=5, rows=4)
    assert [l.strip() for l in screen.display] == ["a", "c", "", "d"]
    screen = replay(b"a\r\nb\r\nc\r\nd\x1b[2;3r\x1b[1T", cols=5, rows=4)
    assert [l.strip() for l in screen.display] == ["a", "", "b", "d"]


def test_private_csi_dropped():
    screen = replay(b"\x1b[>4;2mA\x1b[<uB\x1b[=1uC\x1b[>0qD", cols=10, rows=1)
    assert screen.display[0].strip() == "ABCD"
    assert not any(c.underscore for c in screen.buffer[0].values())
