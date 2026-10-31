"""Expected behaviour for the TUI changes in Claude Code 2.1.312.

Starting point for the owner: these fail until typesetter/ handles the
changes. Screens are synthetic; row layouts marked "assumed" are guesses
from the changelog wording and should be replaced by real captures.
"""
from test_classify import kinds

BOX = ["─" * 99, "❯ ", "─" * 99, "  ⏵⏵ auto mode on"]


def test_click_to_send_hint_under_queued_message():
    # 2.1.312: "Added click to send: in fullscreen, clicking the 'to send now'
    # hint under a queued message sends it right away, as its key does".
    # Layout and colours from a real 2.1.316 capture: the queued message is a
    # grey "❯" row on prompt shading, and the hint is a grey row under it. The
    # hint is one line of UI text: prose on its own row height.
    k = kinds([
        "  9. A street musician played a melancholy tune near the fountain.",
        "",
        "\x1b[38;2;153;153;153;48;2;55;55;55m❯ then say the word done\x1b[0m",
        "  \x1b[38;2;153;153;153mctrl+x ctrl+s to send now\x1b[0m",
        "",
    ] + BOX)
    hint = k["ctrl+x ctrl+s to send now"]
    assert hint["kind"] == "prose" and hint["fixed"]
    assert hint["gutter"] == 2
    # Without the queued message above it, the same words stay monospace.
    k = kinds(["● Bash(ls)", "  ctrl+x ctrl+s to send now", ""] + BOX)
    assert k["ctrl+x ctrl+s to send now"]["kind"] == "mono"
