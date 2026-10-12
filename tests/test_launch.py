import subprocess
import sys
from pathlib import Path

import pytest

from typesetter import server

ROOT = Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:1/?token=t"


@pytest.fixture
def launched(monkeypatch):
    calls = []
    monkeypatch.setattr(server.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    monkeypatch.setattr(server.webbrowser, "open", lambda url: calls.append(["webbrowser", url]))
    return calls


def test_macos_opens_chrome_app_window(monkeypatch, tmp_path, launched):
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.setattr(server.Path, "home", lambda: tmp_path)
    (tmp_path / "Applications" / "Brave Browser.app").mkdir(parents=True)
    real_exists = Path.exists
    # Pretend /Applications has nothing, so the ~/Applications copy is found.
    monkeypatch.setattr(server.Path, "exists",
                        lambda p: real_exists(p) if str(p).startswith(str(tmp_path)) else False)
    server.open_window(URL)
    assert launched == [["open", "-na", "Brave Browser", "--args", f"--app={URL}"]]


def test_macos_without_chromium_uses_default_browser(monkeypatch, launched):
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.setattr(server.Path, "exists", lambda p: False)
    server.open_window(URL)
    assert launched == [["webbrowser", URL]]


def test_linux_opens_chrome_app_window(monkeypatch, launched):
    monkeypatch.setattr(server.sys, "platform", "linux")
    monkeypatch.setattr(server.shutil, "which",
                        lambda name: "/usr/bin/chromium" if name == "chromium" else None)
    server.open_window(URL)
    assert launched == [["/usr/bin/chromium", f"--app={URL}"]]


@pytest.mark.skipif(not (ROOT / ".venv" / "bin" / "python").exists(),
                    reason="launcher needs the repo's .venv")
def test_launcher_through_symlinks(tmp_path):
    # bin/typeset-claude -> ../links/relative -> <repo>/typeset-claude
    (tmp_path / "links").mkdir()
    (tmp_path / "bin").mkdir()
    (tmp_path / "links" / "relative").symlink_to(ROOT / "typeset-claude")
    (tmp_path / "bin" / "typeset-claude").symlink_to(Path("..") / "links" / "relative")
    out = subprocess.run([str(tmp_path / "bin" / "typeset-claude"), "--help"],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert "--option-as-meta" in out.stdout
