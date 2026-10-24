"""Expected behaviour for the TUI changes in Claude Code 2.1.310.

Starting point for the owner: these fail until typesetter/ handles the
changes. Screens are synthetic; row layouts marked "assumed" are guesses
from the changelog wording and should be replaced by real captures.
"""
from test_classify import kinds


def test_symlink_target_in_read_permission_dialog():
    # 2.1.310: "Fixed file read permission prompts not showing where a symbolic
    # link leads". Layout assumed: an arrow row under the path, with no dashed
    # rules (an unpaired ╌ rule would make every row below it code). The link target
    # is a path, so it stays monospace like the other path rows; the
    # surrounding sentences are prose.
    k = kinds([
        "─" * 99,
        " Read file",
        " ~/project/notes.txt",
        " → /etc/hosts",
        "",
        " Do you want to allow reading from notes.txt?",
        " ❯ 1. Yes",
        "   2. No",
    ])
    assert k["Read file"]["kind"] == "prose"
    assert k["~/project/notes.txt"]["kind"] == "mono"
    assert k["→ /etc/hosts"]["kind"] == "mono"
    assert k["Do you want to allow reading from notes.txt?"]["kind"] == "prose"


def test_sandbox_apparmor_warning_keeps_sysctl_command_mono():
    # 2.1.310 (Linux): "/sandbox and the sandbox startup warning now name
    # Ubuntu's AppArmor restriction on user namespaces, and how to lift it".
    # Layout assumed: a "⚠" notice whose fix is a command on the same row,
    # which must not be set in serif.
    k = kinds([
        "⚠ Sandbox unavailable: Ubuntu's AppArmor restricts user namespaces, which",
        "  keeps bubblewrap from starting. To lift it, run:",
        "  sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0",
    ])
    assert k["⚠ Sandbox unavailable: Ubuntu's AppArmor restricts user namespaces, which"]["kind"] == "prose"
    assert k["keeps bubblewrap from starting. To lift it, run:"]["kind"] == "prose"
    assert k["sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0"]["kind"] == "mono"
