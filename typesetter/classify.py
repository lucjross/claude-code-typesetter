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
# A card above the input box (the feedback draft card) is indented one column.
CARD_INDENT = 1
# A tip under the spinner line, e.g. "  ⎿  Tip: Try the Explanatory output style".
SPINNER_TIP = re.compile(r"  ⎿  Tip: ")
# The hint under a queued message (a shaded "❯" row), e.g.
# "  ctrl+x ctrl+s to send now".
SEND_NOW = re.compile(r"  \S.* to send now$")
# Pill drawn over the conversation while scrolled up; covers part of a row.
OVERLAY = re.compile(r"Jump to bottom \(")
# Top-left corner of a markdown table's grid.
TABLE_TOP = "┌─"
# A Web Search call; a long query wraps onto rows indented under the "(".
WEB_SEARCH = "● Web Search("
WEB_SEARCH_INDENT = len(WEB_SEARCH) - 1
# A tool result row: "  ⎿  Did 1 search in 6s".
RESULT = "  ⎿"
DIALOG_RULE_CHARS = set("─▔")
DIALOG_RULE_MIN = 20  # rule characters from column 0
# Dialog option ("❯ 1. Yes", "  2. No").
DIALOG_OPTION = re.compile(r"(?:❯\s+)?\d+\.\s+")
# A slash-command menu row: optional selection marker, then "/command".
MENU_COMMAND = re.compile(r"\s*(?:❯\s+)?/\S")
# Glyphs in column 0 that start a notice: "⚠" for warnings like an
# unrecognised model ID, "※" for the recap shown after stepping away.
NOTICES = set("⚠※")
# Marks a message still waiting to be delivered, under the ctrl+o transcript;
# the full message follows as indented prose.
WAITING = "⏸"
# A dialog or notice row that is code: a path after an optional arrow (a
# symlink target), one filename-like token, or a shell command (a flag,
# "&&", a pipe or key=value). Code quoted in backticks doesn't count.
ARROW_PATH = re.compile(r"(?:→\s+)?(?:~|\.{1,2})?/\S*$")
FILE_TOKEN = re.compile(r"[^\s/]*(?:\w\.\w|[/_=@])\S*$")
SHELL = re.compile(r"(?:^|\s)--?[A-Za-z]|&&|\|\||\s\|\s|\w=\S")
BACKTICKS = re.compile(r"`[^`]*`")
# A labelled value, as in the /design-sync prompt's "Folder:  ~/work/app".
LABEL = re.compile(r"\w[\w ]*:\s+")
# A markdown table row drawn as raw pipes ("| a | b |"), as long tables are.
PIPE_ROW = re.compile(r"\|.*\|$")


def _text(row):
    return "".join(c.data or "" for c in row)


def _cols(row):
    """The row's text with one character per column (a space after a wide
    character), so string indices are columns."""
    return "".join(c.data or " " for c in row)


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


def _is_pinned_prompt(row):
    """Scrolled up, Claude Code pins a dim copy of the prompt to the top
    row: "❯" and text in one colour. A submitted prompt's "❯" is grey and
    its text white."""
    fgs = {c.fg for c in row if c.data and c.data.strip()}
    return len(fgs) == 1 and not fgs & PROSE_FGS


def _looks_like_code(body):
    m = LABEL.match(body)
    value = body[m.end():] if m else body
    if any(ARROW_PATH.match(v) or FILE_TOKEN.match(v) for v in (body, value)):
        return True
    return bool(SHELL.search(BACKTICKS.sub("", body)))


def _continues_link(prev, row, start):
    """True if `row` from `start` carries on the link that ends `prev`, as a
    URL wrapped onto its own row does."""
    end = _last_col(prev)
    link = getattr(row[start], "link", None)
    return (link is not None and end is not None
            and getattr(prev[end], "link", None) == link)


def _cells_ok(row, start, bg="default"):
    """Return (ok, has_prose_cell) for the cells from `start` on."""
    has_prose = False
    for c in row[start:]:
        if not c.data or not c.data.strip():
            continue
        if c.bg != bg or c.reverse:
            return False, has_prose
        if MONO_CHARS.match(c.data) and c.fg not in INLINE_CODE_FGS:
            # Drawn UI; inside inline code it's quoted, like `⎿  Tip:`.
            return False, has_prose
        if c.fg in PROSE_FGS:
            has_prose = True
        elif c.fg not in INLINE_CODE_FGS and not getattr(c, "link", None):
            # Links have their own colour (bright blue) but are prose.
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


def _classify_group(rows, ys, cols, out, bg, continued=False):
    """`ys` is a run of non-blank rows inside one assistant text block or
    user prompt; `bg` is the block's background colour. `continued` means
    the group starts at the top of the screen, inside a block whose first
    line has scrolled off."""
    infos = []
    prev_text_start = None
    prev_was_list = False
    for i, y in enumerate(ys):
        row = rows[y]
        bullet_row = i == 0 and row[0].data in (BULLET, PROMPT)
        indent = BASE_INDENT if bullet_row else _first_col(row)
        ok, has_prose = _cells_ok(row, indent, bg)
        if not ok or not (has_prose or (
                i > 0 and _continues_link(rows[ys[i - 1]], row, indent))):
            return
        if PIPE_ROW.match(_text(row[indent:]).rstrip()):
            return  # columns must stay aligned
        m = None if bullet_row else LIST_MARKER.match(_text(row[indent:]))
        if m:
            text_start = indent + len(m.group(0))
            is_list = True
        elif indent == BASE_INDENT:
            text_start, is_list = indent, False
        elif prev_was_list and indent == prev_text_start:
            text_start, is_list = indent, True  # wrapped list item
        elif continued and i == 0 and BASE_INDENT < indent < cols // 2:
            text_start, is_list = indent, True  # its marker scrolled off
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
    prompts). One-line UI text (welcome header, "⚠"/"※" notices, spinner line, status rows
    around the input box) carries "fixed": True, meaning it keeps terminal
    row height and its own colours, and "right": True if right-aligned.
    A markdown table drawn as a grid is {"kind": "table", "gutter": n,
    "spans": [[x0, x1], ...], "rows": [[y, ...], ...]} on its top border
    row (see _tables) and {"kind": "table", "part": True} on its other rows.
    """
    out = [{"kind": "mono"} for _ in rows]
    block_bg = None  # background of the current text/prompt block, or None
    group = []

    # Rows at the top that are indented continue a block whose first line
    # (bullet or "❯") has scrolled off screen.
    first = next((y for y, r in enumerate(rows) if not _is_blank(r)), None)
    continued = None  # the first row of such a block
    if first is not None and not (rows[first][0].data or " ").strip():
        block_bg = rows[first][0].bg
        continued = first
    prompt_y = None  # where the current prompt block started

    def flush():
        if group and (cursor_y is None or cursor_y not in group):
            _classify_group(rows, group, cols, out, block_bg,
                            continued=group[0] == continued)
        group.clear()

    for y, row in enumerate(rows):
        if row[0].data and row[0].data.strip():
            flush()
            if _is_text_bullet(row):
                block_bg = "default"
            elif _is_prompt_start(row):
                block_bg = row[0].bg
                prompt_y = y
                if y == 0 and _is_pinned_prompt(row):
                    # Set on its own; shaded rows under it are the end of
                    # the real prompt, whose first line has scrolled off.
                    continued = next((r for r in range(1, len(rows))
                                      if not _is_blank(rows[r])), None)
                    continue
            elif row[0].data == WAITING:
                block_bg = "default"  # the marker row itself is status text
                continue
            else:
                block_bg = None
            if block_bg is not None:
                group.append(y)
        elif block_bg is None:
            continue
        elif block_bg != "default" and row[0].bg != block_bg:
            flush()  # prompt shading ended
            block_bg = None
            if prompt_y == 0:
                # Scrolled up, the prompt stays pinned to the top row and
                # the reply under it (after a blank row or not) has lost
                # its "●" line.
                block_bg = "default"
                continued = next((r for r in range(y, len(rows))
                                  if not _is_blank(rows[r])), None)
                if not _is_blank(row):
                    group.append(y)
        elif _is_blank(row):
            flush()
        else:
            group.append(y)
    flush()

    searches, search_results = _web_searches(rows)
    for y, info in searches.items():
        if y != cursor_y:
            out[y] = info
    for table in _tables(rows):
        y0, y1 = table["y0"], table["y1"]
        if cursor_y is None or not y0 <= cursor_y <= y1:
            out[y0] = {"kind": "table", "gutter": table["x0"],
                       "spans": table["spans"], "rows": table["rows"]}
            for y in range(y0 + 1, y1 + 1):
                out[y] = {"kind": "table", "part": True}

    box = _input_box(rows)
    status_rows = set(_status_candidates(rows, cols, box)) | search_results
    # The slash menu opens above the input box; a dialog replaces the box.
    menu = _slash_menu(rows, box[0]) if box else _dialog(rows)
    notices = _notices(rows)
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
        if start is None:
            start = notices.get(y)
        if start is None and y in status_rows:
            start = _status_text_start(row)
        if start is None:
            start = _activity_text_start(row)
        if start is None:
            continue
        info = {"kind": "prose", "gutter": start, "join": False, "fixed": True}
        if _is_right_aligned(row, cols):
            info["right"] = True
        out[y] = info
    return out


def _web_searches(rows):
    """Web Search calls, whose query is a sentence, not code:
        ● Web Search("Spotify Mix transitions Spotify Connect speakers supported devices
                    Sonos Chromecast")
          ⎿  Did 1 search in 6s
    Returns (query, results): query maps the call's rows to prose info,
    serif from the opening quote, wrapped rows joined; results are the "⎿"
    rows under the calls, set like status rows with "⎿" in the gutter.
    """
    query, results = {}, set()
    for y, row in enumerate(rows):
        if not _text(row).startswith(WEB_SEARCH):
            continue
        ys = [y]
        while (ys[-1] + 1 < len(rows)
               and _first_col(rows[ys[-1] + 1]) == WEB_SEARCH_INDENT):
            ys.append(ys[-1] + 1)
        starts = [len(WEB_SEARCH)] + [WEB_SEARCH_INDENT] * (len(ys) - 1)
        if not all(_cells_ok(rows[r], s) == (True, True) for r, s in zip(ys, starts)):
            continue
        for i, (r, s) in enumerate(zip(ys, starts)):
            query[r] = {"kind": "prose", "gutter": s, "join": i > 0, "bg": "default"}
        below = ys[-1] + 1
        if below < len(rows) and _text(rows[below]).startswith(RESULT):
            results.add(below)
    return query, results


def _border(row, xs, left, mid, right):
    """True if `row` draws a table border with junctions at columns `xs`."""
    for x in range(xs[0], xs[-1] + 1):
        c = row[x]
        want = left if x == xs[0] else right if x == xs[-1] else mid if x in xs else "─"
        if c.data != want or c.fg not in PROSE_FGS or c.bg != "default":
            return False
    return True


def _tables(rows):
    """Markdown tables drawn as a box-drawing grid, wholly on screen:
        ● ┌──────────────┬──────────────────────┐
          │     Part     │  What it depends on  │
          ├──────────────┼──────────────────────┤
          │ Browser      │ A Chrome extension   │
          │ automation   │ or the desktop app   │
          └──────────────┴──────────────────────┘
    Every row must have its "│" (or junctions) at the top border's columns
    and nothing outside the grid, so other boxes and code don't match.
    Returns dicts with "y0"/"y1" (border rows), "x0" (the grid's first
    column), "spans" ([start, end) of each column's cells) and "rows" (the
    screen rows of each table row, header first).
    """
    tables = []
    y = 0
    while y < len(rows):
        row = rows[y]
        line = _cols(row)
        x0 = line.find(TABLE_TOP)
        if x0 < 0 or line[:x0].strip() not in ("", BULLET):
            y += 1
            continue
        x1 = line.find("┐", x0)
        if x1 < 0 or line[x1 + 1:].strip():
            y += 1
            continue
        xs = [x0] + [x for x in range(x0 + 1, x1) if line[x] == "┬"] + [x1]
        if not _border(row, xs, "┌", "┬", "┐"):
            y += 1
            continue
        table_rows, current, end = [], [], None
        for b in range(y + 1, len(rows)):
            r = rows[b]
            text = _cols(r)
            if text[:x0].strip() or text[x1 + 1:].strip():
                break
            if _border(r, xs, "└", "┴", "┘"):
                end = b
                break
            if _border(r, xs, "├", "┼", "┤"):
                if not current:
                    break
                table_rows.append(current)
                current = []
            elif all(r[x].data == "│" for x in xs) and "│" not in "".join(
                    text[a + 1:c] for a, c in zip(xs, xs[1:])):
                current.append(b)
            else:
                break
        if end is None or not current:
            y += 1
            continue
        table_rows.append(current)
        tables.append({"y0": y, "y1": end, "x0": x0, "rows": table_rows,
                       "spans": [[a + 1, c] for a, c in zip(xs, xs[1:])]})
        y = end + 1
    return tables


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
    Rows between dashed rules (commands, file contents) and rows that look
    like code (paths, filenames, shell commands) stay monospace. Only
    called when no input box is on screen.
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
        if row[gutter].data in NOTICES:
            gutter += 2  # "⚠ " stays in the gutter, as in _notices
        body = _text(row[gutter:]).strip()
        if (not body or "   " in body or _looks_like_code(body)
                or MONO_CHARS.search(body) or LOGO_CHARS.search(body)):
            continue
        gutters[y] = gutter
    return gutters


def _notices(rows):
    """Map row -> gutter for notices like the startup warning or a recap:
        ⚠ Model "foo-1" isn't recognized · context assumed to be 200k tokens · see
          the docs
        ※ recap: We're rebuilding the bot, and everything is pushed. Next, you
          decide whether to open a pull request.
    Each row is set on its own (a "fixed" row can't hold a wrapped line).
    A notice with columns or drawn UI in any row stays monospace; a row
    that looks like code (a command to run) stays monospace on its own.
    """
    gutters = {}
    for y, row in enumerate(rows):
        if row[0].data not in NOTICES or (row[1].data or " ").strip():
            continue
        ys = [y]
        while (ys[-1] + 1 < len(rows) and not _is_blank(rows[ys[-1] + 1])
               and _first_col(rows[ys[-1] + 1]) == BASE_INDENT):
            ys.append(ys[-1] + 1)
        bodies = [_text(rows[r][BASE_INDENT:]).strip() for r in ys]
        if all(b and "   " not in b and not MONO_CHARS.search(b)
               and not LOGO_CHARS.search(b) for b in bodies):
            gutters.update((r, BASE_INDENT) for r, b in zip(ys, bodies)
                           if r == y or not _looks_like_code(b))
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
        if ((row[0].data in SPINNER_GLYPHS or row[0].data == WAITING)
                and not (row[1].data or "").strip()):
            yield y  # spinner / "Cooked for 3s" line
            # A long one (the compaction row) wraps onto indented words.
            while (y + 1 < len(rows) and _first_col(rows[y + 1]) == BASE_INDENT
                   and (rows[y + 1][BASE_INDENT].data or " ").isalnum()):
                y += 1
                yield y
            if y + 1 < len(rows) and SPINNER_TIP.match(_text(rows[y + 1])):
                yield y + 1  # "⎿" stays in the gutter
    for y in range(1, len(rows)):
        if (rows[y - 1][0].bg != "default"
                and SEND_NOW.match(_text(rows[y]).rstrip())):
            yield y
    if box:
        top, bottom = box
        # Above the box only right-aligned rows ("◐ medium · /effort") and
        # card rows; the slash-command menu opens there too and is handled by
        # _slash_menu. A card's shortcut row ("1: Yes   2: No") is columnar,
        # so _status_text_start leaves it monospace.
        for y in range(max(0, top - STATUS_ABOVE_BOX), top):
            if (_is_right_aligned(rows[y], cols)
                    or _first_col(rows[y]) == CARD_INDENT):
                yield y
        yield from range(bottom + 1, len(rows))


def _activity_text_start(row):
    """Column where a tool's activity row starts, or None:
        ● Waiting 4 seconds · 2s
        ● Listed 1 directory, ran 2 shell commands
    The "●" isn't white like a text block's (grey while running, blinking),
    and the words are a sentence, not a call like "Bash(ls)"."""
    # With the bullet blinked off, the blank cell keeps its grey.
    if len(row) < 3 or row[0].data not in (BULLET, " ") or row[0].fg in BULLET_FGS:
        return None
    if (row[1].data or " ").strip() or not (row[2].data or " ").isalpha():
        return None
    rest = _text(row[2:]).strip()
    if (TOOL_CALL.match(rest) or "(" in rest.split(" ", 1)[0] or "   " in rest
            or MONO_CHARS.search(rest) or LOGO_CHARS.search(rest)):
        return None
    return 2


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
