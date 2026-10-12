"""Record the result of a compatibility run against a Claude Code version.

usage: python tools/record_status.py VERSION passing|failing

Writes the README badge (.github/badges/claude-code.json, a shields.io
endpoint) and, when passing, the "Tested with Claude Code" version in
README.md.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BADGE = ROOT / ".github" / "badges" / "claude-code.json"
README = ROOT / "README.md"
MARKER = re.compile(r"(<!-- claude-code-version -->).*?(<!-- /claude-code-version -->)")


def record(version, result):
    BADGE.parent.mkdir(parents=True, exist_ok=True)
    BADGE.write_text(json.dumps({
        "schemaVersion": 1,
        "label": "Claude Code",
        "message": f"{version} {result}",
        "color": "brightgreen" if result == "passing" else "red",
    }, indent=2) + "\n")
    if result == "passing":
        text = README.read_text()
        new, n = MARKER.subn(rf"\g<1>{version}\g<2>", text)
        if n == 0:
            raise SystemExit("README.md has no claude-code-version marker")
        README.write_text(new)


def main():
    if len(sys.argv) != 3 or sys.argv[2] not in ("passing", "failing"):
        raise SystemExit(__doc__.split("\n\n")[1])
    record(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
