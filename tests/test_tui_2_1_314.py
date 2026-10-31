"""Expected behaviour for the TUI changes in Claude Code 2.1.314.

Starting point for the owner: these fail until typesetter/ handles the
changes. Screens are synthetic; row layouts marked "assumed" are guesses
from the changelog wording and should be replaced by real captures.
"""
from test_classify import kinds

def test_design_sync_upload_prompt():
    # 2.1.314: "Improved the `/design-sync` upload prompt to show the folder,
    # the project and the files it will upload or delete". Layout assumed: a
    # dialog under a "─" rule with a question, labelled lines whose values are
    # paths, and file rows. The question is prose; paths stay monospace.
    k = kinds([
        "─" * 99,
        " Upload design files?",
        "",
        " Folder:  ~/work/app/design",
        " Project: Marketing site",
        " Upload:  src/tokens.css",
        " Delete:  src/old-logo.svg",
        "",
        " Do you want to proceed?",
        " ❯ 1. Yes",
        "   2. No",
    ])
    assert k["Upload design files?"]["kind"] == "prose"
    assert k["Do you want to proceed?"]["kind"] == "prose"
    assert k["Folder:  ~/work/app/design"]["kind"] == "mono"
    assert k["Upload:  src/tokens.css"]["kind"] == "mono"


def test_raw_pipe_table_rows_stay_mono():
    # 2.1.314: "Fixed markdown tables jumping between grid and stacked layouts
    # on half-typed rows while streaming, and long tables falling back to raw
    # pipes". Layout assumed: a long table is drawn as raw "| a | b |" rows
    # under the bullet. Columns must stay aligned, so they stay monospace
    # (the box-drawing grid form already does).
    k = kinds([
        "● Results:",
        "",
        "  | Name | Count |",
        "  | foo  | 3     |",
    ])
    assert k["| Name | Count |"]["kind"] == "mono"
    assert k["| foo  | 3     |"]["kind"] == "mono"
