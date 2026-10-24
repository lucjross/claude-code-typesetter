import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import release  # noqa: E402


@pytest.fixture
def repo(tmp_path, monkeypatch):
    readme = tmp_path / "README.md"
    readme.write_text("Tested with Claude Code <!-- claude-code-version -->2.1.300<!-- /claude-code-version -->.\n")
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "0.1.0"\n')
    monkeypatch.setattr(release, "README", readme)
    monkeypatch.setattr(release, "PYPROJECT", pyproject)
    return tmp_path


def test_appends_tested_claude_code_version(repo):
    full = release.release_version("0.2.0")
    assert full == "0.2.0+cc.2.1.300"
    release.write(full)
    assert 'version = "0.2.0+cc.2.1.300"' in (repo / "pyproject.toml").read_text()


def test_rewrites_an_earlier_release_version(repo):
    release.write("0.2.0+cc.2.1.300")
    release.write("0.3.0+cc.2.1.301")
    assert (repo / "pyproject.toml").read_text().count("version =") == 1
    assert 'version = "0.3.0+cc.2.1.301"' in (repo / "pyproject.toml").read_text()


@pytest.mark.parametrize("bad", ["1.2", "v1.2.3", "1.2.3+cc.2.1.300"])
def test_rejects_anything_but_x_y_z(repo, bad):
    with pytest.raises(SystemExit):
        release.release_version(bad)
