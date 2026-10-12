"""Decide which screen rows of Claude Code's TUI are assistant prose.

Conservative by design: a row is "prose" only when every rule below says so;
anything uncertain stays "mono" and renders exactly like a terminal would.

Observed layout (Claude Code 2.1.x, fullscreen TUI, dark theme):
  ● First line of an assistant text message      <- white bullet at col 0
    continuation rows, indented two columns      <- default fg
    inline `code` is fg #b1b9f9
    fenced code: same indent, syntax colours (named ANSI colours), or all
    #b1b9f9 when there is no language
  ● Bash(echo hi)                                <- tool call, not prose
    ⎿  hi                                        <- tool result
  ❯ a submitted user prompt                      <- shaded background
    wrapped prompt rows keep the shading
Any non-space character in column 0 starts a new block.
"""
import re

BULLET = "●"
PROMPT = "❯"
BULLET_FGS = {"default", "ffffff", "000000"}
PROSE_FGS = {"default", "ffffff", "000000"}
INLINE_CODE_FGS = {"b1b9f9"}
BASE_INDENT = 2
# Right-margin slack when deciding whether a row was soft-wrapped.
WRAP_SLACK = 4

TOOL_CALL = re.compile(r"[A-Za-z_][\w.:-]*\(")
LIST_MARKER = re.compile(r"(?:[-*•◦▪]|\d+[.)]) ")
MONO_CHARS = re.compile(r"[─-╿⎿]")
# Block elements that make up the welcome-header logo.
LOGO_CHARS = re.compile(r"[▀-▟]")
LOGO_MAX_COL = 14
# Spinner / completion line, e.g. "✻ Cooked for 3s".
SPINNER_GLYPHS = set("·✢✳✶✻✽*")
# Status rows: how far above the input box to look, and how many leading
# glyph cells (like "⏵⏵") may precede the words.
STATUS_ABOVE_BOX = 2
STATUS_MAX_GLYPHS = 3
# Pill drawn over the conversation while scrolled up; covers part of a row.
OVERLAY = re.compile(r"Jump to bottom \(")
DIALOG_RULE_CHARS = set("─▔")
DIALOG_RULE_MIN = 20  # rule characters from column 0
# Dialog option ("❯ 1. Yes", "  2. No") and a row that is just a path.
DIALOG_OPTION = re.compile(r"(?:❯\s+)?\d+\.\s+")
PATH_ONLY = re.compile(r"(?:~|\.{1,2})?/\S*$")
# A slash-command menu row: optional selection marker, then "/command".
MENU_COMMAND = re.compile(r"\s*(?:❯\s+)?/\S")


def _text(row):
    return "".join(c.data or "" for c in row)


def _is_blank(row):
    return not _text(row).strip()


def _first_col(row):
    for x, c in enumerate(row):
        if c.data and c.data.strip():
            return x
    return None


def _last_col(row):
    for x in range(len(row) - 1, -1, -1):
        if row[x].data and row[x].data.strip():
            return x
    return None


def _is_text_bullet(row):
    if len(row) < 3 or row[0].data != BULLET or row[0].fg not in BULLET_FGS:
        return False
    rest = _text(row[2:])
    return bool(rest.strip()) and not TOOL_CALL.match(rest)


def _is_prompt_start(row):
    """A submitted user prompt: "❯" in col 0 on a shaded background.

    The live input box also starts with "❯" but has the default background.
    """
    return len(row) > 2 and row[0].data == PROMPT and row[0].bg != "default"


def _cells_ok(row, start, bg="default"):
    """Return (ok, has_prose_cell) for the cells from `start` on."""
    has_prose = False
    for c in row[start:]:
        if not c.data or not c.data.strip():
            continue
        if c.bg != bg or c.reverse or MONO_CHARS.match(c.data):
            return False, has_prose
        if c.fg in PROSE_FGS:
            has_prose = True
        elif c.fg not in INLINE_CODE_FGS:
            return False, has_prose
    return True, has_prose


def mask_overlay(rows):
    """Lift the "Jump to bottom" pill out of the screen.

    Claude Code draws it over the last conversation row while scrolled up.
    Returns (rows, overlay): rows with the pill replaced by "…" on a blank
    background so the row classifies like its paragraph, and
    {"y", "x0", "x1"} locating the pill (or None).
    """
    for y, row in enumerate(rows):
        cols_text = [c.data or "" for c in row]
        line = "".join(ch or "\0" for ch in cols_text)  # one char per column
        m = OVERLAY.search(line)
        if not m:
            continue
        bg = row[m.start()].bg
        x0, x1 = m.start(), m.end()
        while x0 > 0 and row[x0 - 1].bg == bg:
            x0 -= 1
        while x1 < len(row) and row[x1].bg == bg:
            x1 += 1
        blank = row[0]._replace(data=" ", fg="default", bg="default", bold=False,
                                italics=False, underscore=False, strikethrough=False,
                                reverse=False)
        masked = list(row)
        for x in range(x0, x1):
            masked[x] = blank
        if not _is_blank(masked):
            masked[x0] = blank._replace(data="…")  # mark the hidden text
        rows = list(rows)
        rows[y] = masked
        return rows, {"y": y, "x0": x0, "x1": x1}
    return rows, None


def _header_text_start(row):
    """Column where header text starts after the logo, or None.

    Matches the welcome header's "Claude Code vX" and model/plan lines;
    the working-directory line is left monospace.
    """
    logo_end = None
    for x, c in enumerate(row[:LOGO_MAX_COL]):
        if c.data and LOGO_CHARS.match(c.data):
            logo_end = x
    if logo_end is None:
        return None
    offset = _first_col(row[logo_end + 1:])
    if offset is None or offset < 1:
        return None
    start = logo_end + 1 + offset
    rest = _text(row[start:]).strip()
    if rest[:1] in "/~" or MONO_CHARS.search(rest) or LOGO_CHARS.search(rest):
        return None
    return start


def _classify_group(rows, ys, cols, out, bg):
    """`ys` is a run of non-blank rows inside one assistant text block or
    user prompt; `bg` is the block's background colour."""
    infos = []
    prev_text_start = None
    prev_was_list = False
    for i, y in enumerate(ys):
        row = rows[y]
        bullet_row = i == 0 and row[0].data in (BULLET, PROMPT)
        indent = BASE_INDENT if bullet_row else _first_col(row)
        ok, has_prose = _cells_ok(row, indent, bg)
        if not ok or not has_prose:
            return
        m = None if bullet_row else LIST_MARKER.match(_text(row[indent:]))
        if m:
            text_start = indent + len(m.group(0))
            is_list = True
        elif indent == BASE_INDENT:
            text_start, is_list = indent, False
        elif prev_was_list and indent == prev_text_start:
            text_start, is_list = indent, True  # wrapped list item
        else:
            return  # unexplained indentation: probably code
        infos.append((y, indent, text_start, m is not None))
        prev_text_start, prev_was_list = text_start, is_list

    para_start = None
    for i, (y, indent, text_start, has_marker) in enumerate(infos):
        join = False
        if i > 0 and not has_marker and indent == para_start:
            prev = rows[infos[i - 1][0]]
            end = _last_col(prev) + 1
            word = _text(rows[y][indent:]).split(" ", 1)[0]
            join = end + 1 + len(word) > cols - WRAP_SLACK
        if not join:
            para_start = text_start
        out[y] = {"kind": "prose", "gutter": text_start, "join": join, "bg": bg}


def classify(rows, cols, cursor_y=None):
    """rows: list of rows, each a list of pyte Chars `cols` long.

    Returns one dict per row: {"kind": "mono"} or
    {"kind": "prose", "gutter": n, "join": bool, "bg": colour}. `gutter` is
    how many leading cells stay monospace (indent, bullet, list marker);
    `join` means the row is a soft-wrapped continuation of the previous
    prose row; `bg` is the block background ("default" except for user
    prompts). One-line UI text (welcome header, spinner line, status rows
    around the input box) carries "fixed": True, meaning it keeps terminal
    row height and its own colours, and "right": True if right-aligned.
    """
    out = [{"kind": "mono"} for _ in rows]
    block_bg = None  # background of the current text/prompt block, or None
    group = []

    # Rows at the top that are indented continue a block whose first line
    # (bullet or "❯") has scrolled off screen.
    first = next((r for r in rows if not _is_blank(r)), None)
    if first is not None and not (first[0].data or " ").strip():
        block_bg = first[0].bg

    def flush():
        if group and (cursor_y is None or cursor_y not in group):
            _classify_group(rows, group, cols, out, block_bg)
        group.clear()

    for y, row in enumerate(rows):
        if row[0].data and row[0].data.strip():
            flush()
            if _is_text_bullet(row):
                block_bg = "default"
            elif _is_prompt_start(row):
                block_bg = row[0].bg
            else:
                block_bg = None
            if block_bg is not None:
                group.append(y)
        elif block_bg is None:
            continue
        elif block_bg != "default" and row[0].bg != block_bg:
            flush()  # prompt shading ended
            block_bg = None
        elif _is_blank(row):
            flush()
        else:
            group.append(y)
    flush()

    box = _input_box(rows)
    status_rows = set(_status_candidates(rows, cols, box))
    # The slash menu opens above the input box; a dialog replaces the box.
    menu = _slash_menu(rows, box[0]) if box else _dialog(rows)
    if box:
        for y in _input_rows(rows, box):
            # The cursor lives here, so this skips the cursor-row exclusion.
            out[y] = {"kind": "prose", "gutter": BASE_INDENT, "join": False,
                      "fixed": True, "input": True}
    for y, row in enumerate(rows):
        if out[y]["kind"] != "mono" or y == cursor_y:
            continue
        start = menu.get(y)
        if start is None:
            start = _header_text_start(row)
        if start is None and y in status_rows:
            start = _status_text_start(row)
        if start is None:
            continue
        info = {"kind": "prose", "gutter": start, "join": False, "fixed": True}
        if _is_right_aligned(row, cols):
            info["right"] = True
        out[y] = info
    return out


def _input_box(rows):
    """(top, bottom) border rows of the live input box, or None."""
    for y in range(len(rows) - 2, -1, -1):
        if (_text(rows[y]).startswith("─") and rows[y + 1][0].data == PROMPT
                and rows[y + 1][0].bg == "default"):
            for b in range(y + 2, len(rows)):
                if _text(rows[b]).startswith("─"):
                    return y, b
            return None
    return None


def _input_rows(rows, box):
    """Rows of the "❯" input box holding what the user is typing.

    Bash mode shows "!" instead of "❯", and _input_box only matches "❯", so
    typed shell commands stay monospace.
    """
    top, bottom = box
    ys = list(range(top + 1, bottom))
    for i, y in enumerate(ys):
        row = rows[y]
        lead = (row[0].data or " ") if i == 0 else " "
        if (row[0].data or " ") != lead or (row[1].data or " ").strip():
            return []
        if MONO_CHARS.search(_text(row[BASE_INDENT:])):
            return []
    return ys


def _is_right_aligned(row, cols):
    first, last = _first_col(row), _last_col(row)
    return first is not None and first > cols // 2 and last >= cols - WRAP_SLACK


def _slash_menu(rows, top):
    """Map row -> description column for the slash-command menu.

    The menu is the run of non-blank rows directly above the input box:
        ❯ /model           Set the AI model for Claude Code
          /morning         Render the user's morning brief as a styled HTML
                           artifact, or set it up as a recurring task. U…
    Commands stay in the monospace gutter; descriptions go serif from their
    column, so the two columns stay aligned. Returns {} unless every row in
    the run fits that shape.
    """
    ys = []
    y = top - 1
    while y >= 0 and not _is_blank(rows[y]):
        ys.append(y)
        y -= 1
    menu = {}
    desc_col = None
    for y in reversed(ys):
        row = rows[y]
        first = _first_col(row)
        line = _text(row)
        if MENU_COMMAND.match(line):
            desc_col = _after_gap(row, first)
            if desc_col is None:
                return {}
        elif desc_col is None or first != desc_col:
            return {}  # not a wrapped description either
        if MONO_CHARS.search(_text(row[desc_col:])):
            return {}
        menu[y] = desc_col
    return menu


def _dialog(rows):
    """Map row -> gutter for the text of a dialog (permission prompts etc.).

    A dialog takes the input box's place at the bottom of the screen:
        ───────────────────────────────
         Bash command                          <- serif
         ls -la ~/                             <- (or between ╌ rules) mono
        ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
         Do you want to proceed?               <- serif
         ❯ 1. Yes                              <- "❯ 1. " stays in the gutter
    Rows between dashed rules (commands, file contents) and path-only rows
    stay monospace. Only called when no input box is on screen.
    """
    start = None
    for y in range(len(rows) - 1, -1, -1):
        line = _text(rows[y])
        # Permission prompts use "───"; panels like /model use "▔▔▔", which
        # can share its row with a right-aligned hint.
        run = len(line) - len(line.lstrip("".join(DIALOG_RULE_CHARS)))
        if run >= DIALOG_RULE_MIN:
            start = y
            break
    if start is None:
        return {}
    gutters = {}
    in_code = False
    for y in range(start + 1, len(rows)):
        row = rows[y]
        line = _text(row)
        if line.startswith("╌"):
            in_code = not in_code
            continue
        first = _first_col(row)
        if in_code or first is None or first == 0:
            continue
        m = DIALOG_OPTION.match(_text(row[first:]))
        gutter = first + len(m.group(0)) if m else first
        body = _text(row[gutter:]).strip()
        if (not body or PATH_ONLY.match(body) or "   " in body
                or MONO_CHARS.search(body) or LOGO_CHARS.search(body)):
            continue
        gutters[y] = gutter
    return gutters


def _after_gap(row, start):
    """First non-space column after a run of 2+ spaces, scanning from start."""
    spaces = 0
    for x in range(start, len(row)):
        if (row[x].data or " ").strip():
            if spaces >= 2:
                return x
            spaces = 0
        else:
            spaces += 1
    return None


def _status_candidates(rows, cols, box):
    """Rows that may hold one-line status text."""
    for y, row in enumerate(rows):
        if row[0].data in SPINNER_GLYPHS and not (row[1].data or "").strip():
            yield y  # spinner / "Cooked for 3s" line
    if box:
        top, bottom = box
        # Above the box only right-aligned rows ("◐ medium · /effort"); the
        # slash-command menu opens there too and is handled by _slash_menu.
        for y in range(max(0, top - STATUS_ABOVE_BOX), top):
            if _is_right_aligned(rows[y], cols):
                yield y
        yield from range(bottom + 1, len(rows))


def _status_text_start(row):
    """Column where a status row's words begin after its leading glyphs."""
    x = _first_col(row)
    if x is None:
        return None
    glyphs = 0
    while x < len(row) and not (row[x].data or " ").isalnum():
        if (row[x].data or " ").strip():
            glyphs += 1
        x += 1
    if glyphs > STATUS_MAX_GLYPHS or x >= len(row):
        return None
    rest = _text(row[x:]).strip()
    if "   " in rest or MONO_CHARS.search(rest) or LOGO_CHARS.search(rest):
        return None  # columnar (menus, tables) or drawn UI
    return x
