"""Expected behaviour for the TUI changes in Claude Code 2.1.311.

Starting point for the owner: these fail until typesetter/ handles the
changes. Screens are synthetic; row layouts marked "assumed" are guesses
from the changelog wording and should be replaced by real captures.
"""
from test_classify import kinds


def test_explanatory_style_tip_under_spinner():
    # 2.1.311: "Added a tip for the Explanatory output style, shown when you
    # ask Claude for explanations". Layout assumed: like other spinner tips, a
    # "⎿  Tip: ..." row under the spinner line. The sentence is prose, kept on
    # its own row height; the "⎿" stays in the gutter.
    k = kinds([
        "✻ Cooking… (4s)",
        "  ⎿  Tip: Try the Explanatory output style (/output-style) for more detail",
        "",
        "─" * 99,
        "❯ ",
        "─" * 99,
        "  ⏵⏵ auto mode on",
    ])
    tip = k["⎿  Tip: Try the Explanatory output style (/output-style) for more detail"]
    assert tip["kind"] == "prose" and tip["fixed"]
    assert tip["gutter"] == 5


def test_feedback_card_title_is_serif_and_shortcuts_stay_mono():
    # 2.1.311: "Fixed the feedback draft card showing its 1/2/0 and Esc
    # shortcuts while the prompt has text". Layout assumed: the card sits
    # directly above the input box, a question row and a shortcut row. The
    # question is prose; the shortcut row is columnar and stays monospace. With
    # text in the prompt the shortcut row is gone, and the box is still input.
    card = [
        " Send this draft as feedback?",
        " 1: Yes   2: No   0: Dismiss   Esc: Close",
    ]
    box = ["─" * 99, "❯ ", "─" * 99, "  ⏵⏵ auto mode on"]
    k = kinds(card + box)
    assert k["Send this draft as feedback?"]["kind"] == "prose"
    assert k["1: Yes   2: No   0: Dismiss   Esc: Close"]["kind"] == "mono"

    k = kinds(card[:1] + ["─" * 99, "❯ hello", "─" * 99, "  ⏵⏵ auto mode on"])
    assert k["Send this draft as feedback?"]["kind"] == "prose"
    assert k["❯ hello"].get("input")
