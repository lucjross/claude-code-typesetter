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
    # Layout assumed: the queued message is followed by an indented hint row
    # ending in "to send now". The hint is one line of UI text: prose on its
    # own row height, not joined into the queued message's paragraph.
    k = kinds([
        "⏸ Queued: waiting for Claude to finish",
        "  run the tests again",
        "  Enter to send now",
        "",
        "✻ Cooking… (4s)",
        "",
    ] + BOX)
    hint = k["Enter to send now"]
    assert hint["kind"] == "prose" and hint["fixed"]
    assert hint["gutter"] == 2

