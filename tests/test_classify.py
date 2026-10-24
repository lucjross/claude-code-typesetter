from pathlib import Path

import pyte

from typesetter.classify import classify, mask_overlay
from typesetter.terminal import Screen, Stream

FIXTURES = Path(__file__).parent / "fixtures"


def load(name, cols, rows):
    screen = Screen(cols, rows)
    Stream(screen).feed((FIXTURES / name).read_bytes())
    buf = [[screen.buffer[y][x] for x in range(cols)] for y in range(rows)]
    return screen, buf


def text(row):
    return "".join(c.data for c in row).rstrip()


def test_formatting_sample():
    screen, buf = load("formatting-100x60.raw", 100, 60)
    info = classify(buf, 100, cursor_y=screen.cursor.y)
    prose = {y: i for y, i in enumerate(info) if i["kind"] == "prose"}
    by_text = {text(buf[y]).strip(): i for y, i in prose.items()}

    # Heading line (with the bullet) and the wrapped paragraph.
    assert by_text["● Sample Formatting Probe"]["gutter"] == 2
    para = [y for y in prose if "paragraph is long enough" in text(buf[y])][0]
    assert prose[para]["join"] is False
    assert prose[para + 1]["join"] is True
    assert prose[para + 2]["join"] is True

    # List items: marker in gutter, never joined to each other.
    item = by_text["- Second item, with inline_code included"]
    assert item == {"kind": "prose", "gutter": 4, "join": False, "bg": "default"}

    assert by_text["That's the end of the formatting sample."]["join"] is False

    # Code (syntax-coloured and plain) and UI chrome stay monospace.
    mono = [text(buf[y]) for y, i in enumerate(info) if i["kind"] == "mono"]
    for needle in ("def greet", "return message", "plain line one"):
        assert any(needle in m for m in mono), needle
    assert all("print(message)" not in text(buf[y]) for y in prose)


def test_welcome_header():
    screen, buf = load("formatting-100x60.raw", 100, 60)
    info = classify(buf, 100, cursor_y=screen.cursor.y)
    rows = {text(buf[y]).strip(): info[y] for y in range(5)}
    title = next(i for t, i in rows.items() if "Claude Code v" in t)
    model = next(i for t, i in rows.items() if "Claude Pro" in t)
    path = next(i for t, i in rows.items() if "/tmp/" in t)
    for i in (title, model):
        assert i["kind"] == "prose" and i["fixed"] and i["gutter"] == 11
    assert path["kind"] == "mono"


def test_user_prompt():
    screen, buf = load("formatting-100x60.raw", 100, 60)
    info = classify(buf, 100, cursor_y=screen.cursor.y)
    start = next(y for y in range(60) if text(buf[y]).startswith("❯ Without using"))
    first, second, third = info[start:start + 3]
    assert first == {"kind": "prose", "gutter": 2, "join": False, "bg": "373737"}
    assert second["join"] and third["join"]
    assert info[start + 3]["kind"] == "mono"  # blank row after the prompt
    # The live input box ("❯" on the default background) is the input rule.
    box = max(y for y in range(60) if text(buf[y]).startswith("❯"))
    assert box != start and info[box].get("input")


def test_status_rows():
    screen, buf = load("formatting-100x60.raw", 100, 60)
    info = classify(buf, 100, cursor_y=screen.cursor.y)
    find = lambda needle: next(i for y, i in enumerate(info) if needle in text(buf[y]))
    cooked = find("Cooked for 3s")
    assert cooked["kind"] == "prose" and cooked["fixed"] and cooked["gutter"] == 2
    mode = find("auto mode on")
    assert mode["kind"] == "prose" and mode["gutter"] == 5  # after "  ⏵⏵ "


def synthetic(lines, cols=60):
    screen = pyte.Screen(cols, len(lines))
    pyte.ByteStream(screen).feed("\r\n".join(lines).encode())
    return [[screen.buffer[y][x] for x in range(cols)] for y in range(len(lines))]


def test_status_columnar_and_right_aligned():
    buf = synthetic([
        "",
        " " * 40 + "◐ medium · /effort",
        "─" * 60,
        "❯ /mo",
        "─" * 60,
        "  /model        Set the AI model",
        "  ⏸ manual mode on · ? for shortcuts",
    ])
    info = classify(buf, 60)
    assert info[1]["kind"] == "prose" and info[1].get("right")
    assert info[3].get("input")                # live input box
    assert info[5]["kind"] == "mono"           # columnar autocomplete row
    assert info[6]["kind"] == "prose" and info[6]["gutter"] == 4


def test_slash_menu_descriptions():
    buf = synthetic([
        "",
        "  ❯ /model                Set the AI model",
        "    /morning              Render the user's morning brief",
        "                          artifact, or set it up as a task",
        "─" * 60,
        "❯ /mo",
        "─" * 60,
        "  ⏵⏵ auto mode on (shift+tab to cycle)",
    ])
    info = classify(buf, 60)
    for y in (1, 2, 3):
        assert info[y]["kind"] == "prose" and info[y]["fixed"], y
        assert info[y]["gutter"] == 26, y  # descriptions share one column
    assert info[5].get("input")


def test_non_menu_rows_above_input_box_stay_mono():
    buf = synthetic([
        "",
        "  ❯ /model                Set the AI model",
        "      something misaligned here",
        "─" * 60,
        "❯ /mo",
        "─" * 60,
    ])
    info = classify(buf, 60)
    assert info[1]["kind"] == "mono" and info[2]["kind"] == "mono"


def test_reply_continuing_from_offscreen():
    # The reply's "●" line has scrolled off; its list items fill the top.
    screen, buf = load("scrolling-80x24.raw", 80, 24)
    info = classify(buf, 80, cursor_y=screen.cursor.y)
    for y in range(17):
        assert info[y]["kind"] == "prose", (y, text(buf[y]))
        assert info[y]["join"] is False
    assert info[21].get("input")  # input box


def test_jump_to_bottom_overlay():
    buf = synthetic([
        "● Intro line.",
        "",
        "  In the late 15th and 16th centuries, Aldus Manutius and",
        "  refined the roman i\x1b[48;5;236m Jump to bottom (ctrl+End) ↓ \x1b[0mch",
        "─" * 60,
        "❯ ",
        "─" * 60,
    ])
    rows, overlay = mask_overlay(buf)
    assert overlay == {"y": 3, "x0": 21, "x1": 50}
    assert text(rows[3]) == "  refined the roman i…" + " " * 28 + "ch"
    assert rows[2] is buf[2]  # other rows untouched
    info = classify(rows, 60)
    assert info[2]["kind"] == "prose" and info[3]["kind"] == "prose"


def test_no_overlay():
    buf = synthetic(["● Just text.", "─" * 60, "❯ ", "─" * 60])
    rows, overlay = mask_overlay(buf)
    assert overlay is None and rows is buf


def test_overlay_on_blank_row():
    # The pill can sit on the blank row between paragraphs.
    buf = synthetic([
        "● Intro line.",
        "",
        "  At the end of the eighteenth century, Bodoni and Didot.",
        "             \x1b[48;5;236m Jump to bottom (ctrl+End) ↓ \x1b[0m",
        "─" * 60,
        "❯ ",
        "─" * 60,
    ])
    rows, overlay = mask_overlay(buf)
    assert overlay["y"] == 3 and not text(rows[3])
    assert classify(rows, 60)[2]["kind"] == "prose"


DASH = "╌" * 99


def kinds(lines, cols=100):
    buf = synthetic(lines, cols)
    info = classify(buf, cols)
    return {text(buf[y]).strip(): info[y] for y in range(len(lines)) if text(buf[y]).strip()}


def test_bash_permission_dialog():
    k = kinds([
        "  ⎿  $ ls -la ~/ && ls -la ~/edit-test.txt 2>/dev/null",
        "",
        "─" * 99,
        " Bash command",
        " Tip: auto mode handles these prompts for you",
        " List home directory and check for an existing test file",
        DASH,
        ' ls -la ~/ && ls -la ~/edit-test.txt 2>/dev/null; echo "exit: $?"',
        DASH,
        " This command requires approval",
        "",
        " Do you want to proceed?",
        " ❯ 1. Yes",
        '   2. Yes, and allow access to /home/luc and "echo" commands',
        "   4. No",
    ])
    for t in ("Bash command", "Do you want to proceed?",
              "List home directory and check for an existing test file"):
        assert k[t]["kind"] == "prose", t
    assert k["❯ 1. Yes"]["gutter"] == 6
    assert k["4. No"]["kind"] == "prose"
    assert k['ls -la ~/ && ls -la ~/edit-test.txt 2>/dev/null; echo "exit: $?"']["kind"] == "mono"
    assert k["⎿  $ ls -la ~/ && ls -la ~/edit-test.txt 2>/dev/null"]["kind"] == "mono"


def test_create_file_dialog():
    k = kinds([
        "● Write(~/edit-test.txt)",
        "",
        "─" * 99,
        " Create file",
        " ../../../../../../home/luc/edit-test.txt",
        DASH,
        "  1 This is a test file created to check the native file tools.",
        "  2",
        "  3 Line two: the quick brown fox jumps over the lazy dog.",
        DASH,
        " Do you want to create edit-test.txt?",
        " ❯ 1. Yes",
        "   2. Yes, and switch to accept edits (auto-approve file edits) for this",
        "      session; Yes, and always allow access to /home/luc (shift+tab)",
        "   3. No",
    ])
    assert k["Create file"]["kind"] == "prose"
    assert k["../../../../../../home/luc/edit-test.txt"]["kind"] == "mono"
    assert k["1 This is a test file created to check the native file tools."]["kind"] == "mono"
    assert k["Do you want to create edit-test.txt?"]["kind"] == "prose"
    wrapped = k["session; Yes, and always allow access to /home/luc (shift+tab)"]
    assert wrapped["kind"] == "prose" and wrapped["gutter"] == 6
    assert k["● Write(~/edit-test.txt)"]["kind"] == "mono"


def test_input_box_means_no_dialog():
    k = kinds(["─" * 99, "❯ hello", "─" * 99, "  ⏵⏵ auto mode on"])
    assert k["❯ hello"].get("input")
    assert k["⏵⏵ auto mode on"]["gutter"] == 5  # status rule, not dialog rule


def test_input_box_rows():
    buf = synthetic([
        "─" * 60,
        "❯ first line of a long message",
        "  second line",
        "─" * 60,
        "  ⏵⏵ auto mode on",
    ])
    info = classify(buf, 60, cursor_y=2)  # cursor in the box is fine
    for y in (1, 2):
        assert info[y] == {"kind": "prose", "gutter": 2, "join": False,
                           "fixed": True, "input": True}


def test_bash_mode_input_stays_mono():
    buf = synthetic(["─" * 60, "! ls -la", "─" * 60, "  ! for bash mode"])
    assert classify(buf, 60, cursor_y=1)[1]["kind"] == "mono"


def test_panel_with_block_rule():
    # /model draws its panel under a "▔▔▔" rule instead of "───".
    k = kinds([
        "▔" * 70 + "  ◐ medium · /effort",  # hint shares the rule's row
        "   Select model",
        "   Switch between Claude models. Your pick becomes the default.",
        "",
        "   ❯ 5.  Haiku 5.5 ✔            Fastest for quick answers",
        "   Enter to set as default · s to use this session only · Esc to cancel",
    ])
    assert k["Select model"]["kind"] == "prose"
    assert k["❯ 5.  Haiku 5.5 ✔            Fastest for quick answers"]["kind"] == "mono"
    assert k["Enter to set as default · s to use this session only · Esc to cancel"]["kind"] == "prose"


def test_viewing_a_subagent():
    # Viewing a subagent (from /tasks): the input box border carries the
    # agent's name, and the agent tree (whose breadcrumb 2.1.300 fixed) sits
    # below the status row. Real 2.1.301 capture.
    screen, buf = load("agent-view-100x30.raw", 100, 30)
    info = classify(buf, 100, None if screen.cursor.hidden else screen.cursor.y)
    k = {text(r).strip(): i for r, i in zip(buf, info) if text(r)}
    box = next(t for t in k if t.startswith("❯") and "Message @general-purpose" in t)
    assert k[box].get("input")  # the input box is still found
    assert k["◯ main"]["kind"] == "prose" and k["◯ main"]["fixed"]
    agent = next(t for t in k if t.startswith("● general-purpose"))
    assert k[agent]["kind"] == "mono"  # columnar: name, task, time, tokens


def test_unrecognized_model_warning():
    # 2.1.299 moved this warning under the welcome header; it wraps with a
    # two-column indent and keeps its own (dim) colours.
    screen, buf = load("unrecognized-model-100x30.raw", 100, 30)
    info = classify(buf, 100, None if screen.cursor.hidden else screen.cursor.y)
    k = {text(r).strip(): i for r, i in zip(buf, info) if text(r)}
    warning = next(t for t in k if t.startswith("⚠ Model"))
    for line in (warning, "the docs"):
        assert k[line]["kind"] == "prose" and k[line]["fixed"]
        assert k[line]["gutter"] == 2
    assert k[next(t for t in k if t.startswith("▝▝"))]["kind"] == "mono"  # cwd row


def test_recap():
    # Drawn like Fs() in the 2.1.304 bundle: dim "※", bold "recap: ", then
    # dim italic text wrapped under a two-column indent.
    buf = synthetic([
        "\x1b[2m※ \x1b[1mrecap: \x1b[22;2;3mWe're rebuilding the bot, and everything is pushed. Next,",
        "\x1b[2;3m  you decide whether I should open a pull request for that branch.\x1b[0m",
        "",
        "─" * 80,
        "❯ ",
        "─" * 80,
    ], cols=80)
    info = classify(buf, 80, cursor_y=4)
    for y in (0, 1):
        assert info[y] == {"kind": "prose", "gutter": 2, "join": False, "fixed": True}, y


def test_notice_with_columns_stays_mono():
    buf = synthetic([
        "⚠ Two things went wrong:",
        "  first        second",
    ])
    info = classify(buf, 60)
    assert info[0]["kind"] == "mono" and info[1]["kind"] == "mono"


def test_update_installed_beside_clear_hint():
    # 2.1.299 shows "Update installed" beside the idle hint, joined with " · ".
    # Strings are from the 2.1.301 bundle; the row's placement is assumed.
    buf = synthetic([
        "─" * 100,
        "❯ ",
        "─" * 100,
        "  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents",
        "  68k uncached · /clear to start fresh · ✓ Update installed · Restart to apply",
    ], cols=100)
    info = classify(buf, 100, cursor_y=1)
    assert info[4]["kind"] == "prose" and info[4]["fixed"]


def test_links_in_a_reply():
    # Claude Code draws links (bare URLs and markdown links alike) in bright
    # blue inside OSC 8 hyperlinks. Real 2.1.301 capture.
    screen, buf = load("links-100x30.raw", 100, 30)
    info = classify(buf, 100, None if screen.cursor.hidden else screen.cursor.y)
    y = next(y for y, r in enumerate(buf) if text(r).startswith("● Bare"))
    assert info[y]["kind"] == "prose"
    assert {c.link for c in buf[y] if c.link} == {"https://example.com/bare-url",
                                                  "https://example.org/named"}


# --- Claude Code 2.1.302 -------------------------------------------------
# Synthetic screen: the layout is assumed from the changelog, not captured.


def test_wrapped_backtick_url_is_one_link():
    # 2.1.302: "URLs written in backticks being clickable only on their first
    # row when they wrap; the whole URL is now one link". A URL in backticks
    # (inline-code colour) inside an OSC 8 link that wraps onto the next row:
    # both rows are prose, the second joins the first, and the link spans both.
    url = "https://example.com/a/very/long/path/that/wraps"
    osc = lambda s: f"\x1b]8;;{url}\x1b\\\x1b[38;2;177;185;249m{s}\x1b[39m\x1b]8;;\x1b\\"
    screen = Screen(40, 2)
    Stream(screen).feed(("● See " + osc(url[:30]) + "\r\n  " + osc(url[30:])).encode())
    buf = [[screen.buffer[y][x] for x in range(40)] for y in range(2)]
    info = classify(buf, 40)
    assert info[0]["kind"] == "prose" and info[1]["kind"] == "prose"
    assert info[1]["join"] is True
    assert {c.link for r in buf for c in r if c.link} == {url}


# --- Claude Code 2.1.306 review (changelog 2.1.304 -> 2.1.306) -------------
# The screens below are synthetic: no real capture of these 2.1.305 screens
# exists yet, so wording and placement are assumed from the changelog.
# Expected to fail until the classifier handles them.


def test_usage_warning_fixes():
    # 2.1.305: "Improved `/usage`: each warning is now a one-line fix that
    # names its source, and `f` applies the fixes". Each fix is one sentence
    # of prose; the source (a setting or env var) is code and stays mono.
    k = kinds([
        "▔" * 70,
        "   Usage",
        "",
        "   ⚠ Unset CLAUDE_CODE_FOO in ~/.zshrc to stop the extra spend",
        "   ⚠ Remove the unused rule Bash(*) from .claude/settings.json",
        "",
        "   f to apply fixes · Esc to close",
    ])
    assert k["Usage"]["kind"] == "prose"
    for line in ("⚠ Unset CLAUDE_CODE_FOO in ~/.zshrc to stop the extra spend",
                 "⚠ Remove the unused rule Bash(*) from .claude/settings.json"):
        assert k[line]["kind"] == "prose" and k[line]["fixed"], line
        assert k[line]["gutter"] == 5, line  # "⚠ " stays in the gutter
    assert k["f to apply fixes · Esc to close"]["kind"] == "prose"


def test_artifacts_delete_confirmation():
    # 2.1.305: "`/artifacts` delete confirmation takes 1 or Enter to keep, 2
    # to delete, and Esc to cancel". Question and key hint are prose; the
    # artifact name is a title and stays mono.
    k = kinds([
        "─" * 80,
        " Delete artifact?",
        " quarterly-report.html",
        "",
        " ❯ 1. Keep",
        "   2. Delete",
        "",
        " 1/Enter to keep · 2 to delete · Esc to cancel",
    ], cols=80)
    assert k["Delete artifact?"]["kind"] == "prose"
    assert k["quarterly-report.html"]["kind"] == "mono"
    assert k["❯ 1. Keep"]["gutter"] == 6
    assert k["2. Delete"]["kind"] == "prose"
    assert k["1/Enter to keep · 2 to delete · Esc to cancel"]["kind"] == "prose"


# Claude Code 2.1.308 changelog (2.1.307): "Fixed `/permissions` > Recently
# denied not showing the denied shell command ... approving a row now names
# the command, not its description". The layout below is a guess; adjust it
# to a real capture. The command is code, so it must stay monospace, while
# the surrounding labels and the approval prompt are prose.
def test_recently_denied_shows_command_mono():
    k = kinds([
        "─" * 99,
        " Recently denied",
        " Commands auto mode denied. Press enter to approve a row.",
        "",
        " ❯ git push --force origin main",
        "   rm -rf node_modules && npm ci",
        "",
        " Approve `git push --force origin main`?",
        " ❯ 1. Yes",
        "   2. No",
    ])
    assert k["Recently denied"]["kind"] == "prose"
    assert k["Commands auto mode denied. Press enter to approve a row."]["kind"] == "prose"
    assert k["❯ git push --force origin main"]["kind"] == "mono"
    assert k["rm -rf node_modules && npm ci"]["kind"] == "mono"
    assert k["Approve `git push --force origin main`?"]["kind"] == "prose"
    assert k["❯ 1. Yes"]["gutter"] == 6
