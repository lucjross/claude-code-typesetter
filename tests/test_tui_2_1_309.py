"""Behaviour wanted for the TUI changes in Claude Code 2.1.309.

Starting point for the owner: these screens are synthetic guesses at the new
layouts (no real capture yet), so adjust them against a real 2.1.309 capture
before implementing. They are expected to fail until the wrapper handles the
changes.
"""
from test_classify import kinds, synthetic, text  # noqa: F401


def test_transcript_waiting_messages():
    # 2.1.309: "Fixed ctrl+o not showing messages from other agents and
    # sessions that are still waiting to be delivered; they now appear in full
    # under the transcript, marked as waiting"
    # Assumed layout: a one-line "waiting" marker in column 0 (UI chrome, like
    # the spinner line, keeps its row height), then the full message as
    # indented, soft-wrapped prose.
    k = kinds([
        "● Bash(git status)",
        "  ⎿  On branch main",
        "",
        "⏸ Waiting to be delivered · from @reviewer",
        "  I looked through the diff and found two places where the retry",
        "  logic can loop forever when the server keeps answering 429.",
    ], cols=64)
    marker = k["⏸ Waiting to be delivered · from @reviewer"]
    assert marker["kind"] == "prose" and marker["fixed"] and marker["gutter"] == 2
    body = k["I looked through the diff and found two places where the retry"]
    assert body["kind"] == "prose" and body["gutter"] == 2
    assert k["logic can loop forever when the server keeps answering 429."]["join"]
