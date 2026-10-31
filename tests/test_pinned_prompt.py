"""Scrolled up, Claude Code pins a dim copy of the conversation's prompt to
the top row. Layouts and colours from Claude Code 2.1.316 captures."""
from test_classify import kinds


PINNED = "\x1b[38;2;80;80;80;48;2;55;55;55m❯ Without using tools, reply with exactly the markdown\x1b[0m"


def test_scrolled_up_reply_after_blank_row_under_pinned_prompt():
    # The pinned prompt can be followed by a blank row before the reply's
    # continuation. Layout and colours from 2.1.316.
    k = kinds([
        PINNED,
        "",
        "  Cause: while a tool runs, Claude Code shows an activity row like this one,",
        "  which blinks.",
        "",
        "  Fix: these activity rows are now one-line serif rows.",
    ], cols=80)
    assert k["Cause: while a tool runs, Claude Code shows an activity row like this one,"]["kind"] == "prose"
    assert k["which blinks."]["join"] is True
    assert k["Fix: these activity rows are now one-line serif rows."]["kind"] == "prose"


def test_prompt_tail_under_pinned_prompt():
    # Scrolled further up, the pinned copy sits over the end of the real
    # prompt (shaded, white text), whose first line has scrolled off.
    shaded = "\x1b[48;2;55;55;55m  \x1b[38;2;255;255;255mShould I open a PR?\x1b[39m          \x1b[0m"
    k = kinds([PINNED, shaded, "", "● I've fixed the flicker on a new branch."], cols=80)
    assert k["❯ Without using tools, reply with exactly the markdown"]["kind"] == "mono"
    tail = k["Should I open a PR?"]
    assert tail["kind"] == "prose" and tail["bg"] != "default"
    assert k["● I've fixed the flicker on a new branch."]["kind"] == "prose"
