"""Expected behaviour for the TUI changes in Claude Code 2.1.316.

Starting point for the owner. NOTE: unlike earlier releases, these pass
against the current typesetter/ (the changes reuse elements it already
recognises), so they act as regression guards until real captures show
otherwise. Screens are synthetic; row layouts marked "assumed" are guesses
from the changelog wording and should be replaced by real captures.
"""
from test_classify import kinds

BOX = ["─" * 99, "❯ ", "─" * 99]


def test_hold_space_hint_is_serif_status_text():
    # 2.1.316: "Fixed the 'hold space to speak' hint using up its three
    # showings in one session, and showing an empty key when push-to-talk is
    # unbound". Layout assumed: a one-line hint in the footer area below the
    # input box, like the other status rows. It is prose, on its own row height.
    k = kinds(BOX + ["  hold space to speak"])
    hint = k["hold space to speak"]
    assert hint["kind"] == "prose" and hint["fixed"]
    assert hint["gutter"] == 2


def test_model_warning_mid_session_is_serif_notice():
    # 2.1.316: "Fixed `/model <id>` not warning when the model isn't
    # recognized by this version and auto-compact will assume a 200K context
    # window". Layout assumed: the same "⚠" notice as the startup warning, now
    # also drawn in the conversation after /model, wrapped under a two-column
    # indent, directly above the input box.
    k = kinds([
        "⚠ Model \"foo-1\" isn't recognized · context assumed to be 200k tokens ·",
        "  auto-compact will use that window",
        "",
        *BOX,
        "  ⏵⏵ auto mode on",
    ])
    for line in ("⚠ Model \"foo-1\" isn't recognized · context assumed to be 200k tokens ·",
                 "auto-compact will use that window"):
        assert k[line]["kind"] == "prose" and k[line]["fixed"], line
        assert k[line]["gutter"] == 2, line


def test_first_run_security_notes_wrap_in_narrow_terminal():
    # 2.1.316: "Fixed first-run setup dropping words from the security notes
    # and the terminal-setup explanation in narrow terminals". Layout assumed:
    # a first-run dialog (no input box) under a rule, with prose that now
    # wraps onto indented rows instead of losing words. Each wrapped row is
    # serif, set on its own row (fixed), with the common indent as gutter.
    k = kinds([
        "─" * 40,
        " Security notes:",
        "",
        " 1. Claude can make mistakes",
        "    You should always review",
        "    Claude's responses, especially",
        "    when running code.",
        "",
        " Press Enter to continue",
    ], cols=40)
    for line in ("Security notes:", "Claude's responses, especially", "when running code.",
                 "Press Enter to continue"):
        assert k[line]["kind"] == "prose" and k[line]["fixed"], line
    assert k["You should always review"]["kind"] == "prose"
    assert k["You should always review"]["gutter"] == 4
