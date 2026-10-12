import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import record_status  # noqa: E402


@pytest.fixture
def repo(tmp_path, monkeypatch):
    readme = tmp_path / "README.md"
    readme.write_text("Tested with Claude Code <!-- claude-code-version -->2.1.0<!-- /claude-code-version -->.\n")
    monkeypatch.setattr(record_status, "README", readme)
    monkeypatch.setattr(record_status, "BADGE", tmp_path / "badges" / "claude-code.json")
    return tmp_path


def test_passing_updates_badge_and_readme(repo):
    record_status.record("2.2.0", "passing")
    badge = json.loads((repo / "badges" / "claude-code.json").read_text())
    assert badge["message"] == "2.2.0 passing" and badge["color"] == "brightgreen"
    assert "-->2.2.0<!--" in (repo / "README.md").read_text()


def test_failing_keeps_last_passing_version(repo):
    record_status.record("2.2.0", "failing")
    badge = json.loads((repo / "badges" / "claude-code.json").read_text())
    assert badge["message"] == "2.2.0 failing" and badge["color"] == "red"
    assert "-->2.1.0<!--" in (repo / "README.md").read_text()
