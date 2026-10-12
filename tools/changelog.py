"""Print Claude Code changelog entries newer than one version, up to another.

usage: python tools/changelog.py SINCE UNTIL [--file CHANGELOG.md]

Without --file, fetches CHANGELOG.md from github.com/anthropics/claude-code.
Versions are compared numerically; SINCE itself is excluded.
"""
import argparse
import re
import sys
import urllib.request

URL = "https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md"
HEADING = re.compile(r"^## (\d+(?:\.\d+)*)\s*$")


def parse(version):
    return tuple(int(p) for p in version.split("."))


def sections(changelog):
    """Yield (version, text) for each "## x.y.z" section."""
    version, lines = None, []
    for line in changelog.splitlines():
        m = HEADING.match(line)
        if m:
            if version:
                yield version, "\n".join(lines).strip()
            version, lines = m.group(1), []
        elif version:
            lines.append(line)
    if version:
        yield version, "\n".join(lines).strip()


def excerpt(changelog, since, until):
    lo, hi = parse(since), parse(until)
    out = [f"## {v}\n\n{body}" for v, body in sections(changelog) if lo < parse(v) <= hi]
    return "\n\n".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("since")
    p.add_argument("until")
    p.add_argument("--file")
    args = p.parse_args()
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    else:
        with urllib.request.urlopen(URL, timeout=30) as r:
            text = r.read().decode("utf-8")
    result = excerpt(text, args.since, args.until)
    if not result:
        print(f"No changelog entries between {args.since} and {args.until}.", file=sys.stderr)
    print(result)


if __name__ == "__main__":
    main()
