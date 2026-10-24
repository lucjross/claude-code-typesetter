"""Starter tests for the TUI changes in Claude Code 2.1.301.

Screens are synthetic: the wording and layout are guesses from the release
notes, not captures. Adjust them against a real 2.1.301 capture. These are
expected to fail until typesetter/classify.py handles the changes.
"""
from test_classify import synthetic

from typesetter.classify import classify


def test_compaction_row_in_resumed_session():
    # 2.1.301: "Fixed the compaction row in a resumed session offering ctrl+o
    # for history that is not loaded; it now says where the earlier messages
    # are saved, and also shows in fullscreen"
    # The row now carries a saved-to location, so it is long enough to wrap;
    # both rows should be set in serif like other one-line status text, with
    # the wrapped row indented under the words.
    buf = synthetic([
        "✻ Conversation compacted · earlier messages are saved in the session",
        "  transcript file under your Claude config directory",
        "",
        "─" * 70,
        "❯ ",
        "─" * 70,
    ], cols=70)
    info = classify(buf, 70, cursor_y=4)
    for y in (0, 1):
        assert info[y]["kind"] == "prose" and info[y]["fixed"], y
        assert info[y]["gutter"] == 2, y

