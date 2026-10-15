"""Starter tests for TUI changes in Claude Code 2.1.300.

Expected to fail until typesetter/classify.py handles them. The screen
layouts are assumptions; check them against a real capture before relying on them.
"""
from test_classify import synthetic

from typesetter.classify import classify


def test_agent_breadcrumb_when_viewing_a_child():
    # 2.1.300: "Fixed a completed parent agent dropping off the breadcrumb
    # (its child shown re-rooted at top level) while you were viewing the child"
    # and "Added `$.ui.view({ agentId })` for mods: shows an agent's transcript in
    # the main view". Viewing an agent's transcript puts a breadcrumb of the
    # agent chain on a one-line row; it should be set in serif like other
    # one-line UI text (fixed to the terminal row height), not left monospace.
    buf = synthetic([
        "  main › researcher › grep-agent",
        "",
        "● Searching the repository for the config loader.",
        "",
        "─" * 60,
        "❯ ",
        "─" * 60,
        "  ⏵⏵ auto mode on (shift+tab to cycle)",
    ])
    info = classify(buf, 60, cursor_y=5)
    assert info[0]["kind"] == "prose" and info[0].get("fixed")
    assert info[0]["gutter"] == 2
    assert info[2]["kind"] == "prose"  # transcript text is unaffected
