"""Set the package version for a release.

usage: python tools/release.py X.Y.Z

Writes X.Y.Z+cc.<Claude Code version> to pyproject.toml, taking the Claude
Code version from README.md's "Tested with" marker (the last version the
compatibility tests passed on), and prints it. The local-version suffix
(`+cc.2.1.300`) keeps each part numeric, so versions sort correctly.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
README = ROOT / "README.md"
MARKER = re.compile(r"<!-- claude-code-version -->(.*?)<!-- /claude-code-version -->")
VERSION_LINE = re.compile(r'^version = ".*"$', re.M)


def release_version(version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(f"version must be X.Y.Z, not {version!r}")
    m = MARKER.search(README.read_text())
    if not m:
        raise SystemExit("README.md has no claude-code-version marker")
    return f"{version}+cc.{m.group(1).strip()}"


def write(full):
    text = PYPROJECT.read_text()
    new, n = VERSION_LINE.subn(f'version = "{full}"', text, count=1)
    if n == 0:
        raise SystemExit("pyproject.toml has no version line")
    PYPROJECT.write_text(new)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__.split("\n\n")[1])
    full = release_version(sys.argv[1])
    write(full)
    print(full)


if __name__ == "__main__":
    main()
