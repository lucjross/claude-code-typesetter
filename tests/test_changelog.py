import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from changelog import excerpt  # noqa: E402

SAMPLE = """# Changelog

## 2.1.10

- Ten

## 2.1.9

- Nine

## 2.1.8

- Eight
"""


def test_excerpt_range_excludes_since():
    out = excerpt(SAMPLE, "2.1.8", "2.1.10")
    assert "## 2.1.10" in out and "## 2.1.9" in out and "Eight" not in out


def test_numeric_comparison():
    # 2.1.10 > 2.1.9 numerically, not as strings.
    assert excerpt(SAMPLE, "2.1.9", "2.1.10").strip() == "## 2.1.10\n\n- Ten"


def test_no_entries():
    assert excerpt(SAMPLE, "2.1.10", "2.1.10") == ""
