# claude-code-typesetter

[![CI](https://github.com/lucjross/claude-code-typesetter/actions/workflows/ci.yml/badge.svg)](https://github.com/lucjross/claude-code-typesetter/actions/workflows/ci.yml)
[![Claude Code](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Flucjross%2Fclaude-code-typesetter%2Fmain%2F.github%2Fbadges%2Fclaude-code.json)](https://github.com/lucjross/claude-code-typesetter/actions/workflows/claude-code-watch.yml)

Run [Claude Code](https://github.com/anthropics/claude-code) in a browser
window where prose is set in a serif font and code stays monospace.

An unofficial wrapper, not affiliated with Anthropic.

The real `claude` TUI runs unmodified in a pseudo-terminal, so everything
works as usual: slash commands, `/model`, Shift+Tab mode switching,
permission prompts, your login and settings. The wrapper only changes how
the screen is drawn.

## Install

Requires Linux or macOS, Python 3.10+, and Claude Code (`claude`) on your
PATH. Tested with Claude Code <!-- claude-code-version -->2.1.299<!-- /claude-code-version -->;
new releases are checked daily (see [the release watch](#claude-code-release-watch)). It opens in a Chrome, Chromium, Edge or Brave app window if one is
installed, otherwise in your default browser. Windows isn't supported
natively (it needs Unix pseudo-terminals); WSL should work.

```sh
curl -fsSL https://raw.githubusercontent.com/lucjross/claude-code-typesetter/main/install.sh | bash
```

[`install.sh`](install.sh) is short; to read it before running it:

```sh
curl -fsSLO https://raw.githubusercontent.com/lucjross/claude-code-typesetter/main/install.sh
less install.sh && bash install.sh
```

It uses pipx if you have it; otherwise it installs into
`~/.local/share/claude-code-typesetter` and links `typeset-claude` into
`~/.local/bin`. Run it again to update. To uninstall, run
`pipx uninstall claude-code-typesetter`, or delete those two paths.

With pipx directly:

```sh
pipx install https://github.com/lucjross/claude-code-typesetter/archive/refs/heads/main.tar.gz
```

From a clone, for development:

```sh
git clone https://github.com/lucjross/claude-code-typesetter
cd claude-code-typesetter
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./typeset-claude
```

## Use

```sh
typeset-claude            # in your project directory
typeset-claude --resume   # unknown flags go to claude
```

It opens a browser app window. Closing the window ends the session (after a
10 second grace period, so reloading is fine).

| Option | Default |
| --- | --- |
| `--serif FONTS` | Charter, Bitstream Charter, Iowan Old Style, Georgia, serif |
| `--mono FONTS` | JetBrains Mono, DejaVu Sans Mono, Liberation Mono, monospace |
| `--size PX` | 15 (monospace size) |
| `--serif-scale N` | 1.12 (serif size relative to `--size`) |
| `--no-browser` | print the URL instead of opening a window |
| `--port N` | random |
| `--option-as-meta` | off: on macOS, Option+key types special characters (as in Terminal.app); with this flag it sends Alt+key to Claude Code. Option+Enter, Backspace and arrows act as Alt either way. |

The server listens on 127.0.0.1 only and requires a random token in the URL.

## How it works

- `typesetter/terminal.py` emulates the terminal with
  [pyte](https://github.com/selectel/pyte), plus fixes for what Claude Code
  sends that pyte lacks (scroll-region SU/SD, `CSI >`/`<`/`=` sequences).
- `typesetter/classify.py` decides, row by row, what is prose. It is
  conservative: anything it can't positively identify stays monospace and
  looks exactly as in a terminal. It recognises assistant text (`●` blocks,
  with code blocks and syntax-coloured lines left monospace), submitted
  prompts, the input box, the welcome header, spinner and status lines,
  slash-menu descriptions and dialogs (with commands, file contents and
  paths left monospace).
- `typesetter/server.py` streams classified rows to the page over a
  WebSocket; `typesetter/keys.py` turns key presses back into terminal input.
- `typesetter/static/index.html` reflows soft-wrapped prose rows into serif
  paragraphs and keeps everything else on the terminal grid.

The rules are tuned for Claude Code's dark theme and its fullscreen TUI;
`typeset-claude` starts `claude` with `--settings '{"tui": "fullscreen"}'`
whatever your own settings say.

## Tests

```sh
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q
```

`tests/test_live.py` checks the rules against your installed Claude Code:

```sh
.venv/bin/python tools/capture.py /tmp/captures     # sends a few short Haiku prompts
CAPTURE_DIR=/tmp/captures .venv/bin/python -m pytest -q tests/test_live.py
```

## Claude Code release watch

`.github/workflows/claude-code-watch.yml` runs daily. When a new Claude Code
version is on npm (compared with `.claude-code-version`), it:

1. captures the new TUI and runs all tests; if anything fails, a Claude agent
   investigates and opens a fix PR (or an issue if it can't fix it);
2. has a Claude agent review the release notes for TUI changes, open an issue
   mentioning the repo owner, and push a branch of starter tests for them;
3. records the version so it isn't processed again, and updates the Claude
   Code badge above (and, if the tests passed, the "Tested with" version).
   A fix PR updates them too once its tests pass.

Setup:

1. Run `claude setup-token` and add the token as the repository secret
   `CLAUDE_CODE_OAUTH_TOKEN`. Runs count against that account's usage.
2. In Settings → Actions → General, allow GitHub Actions to create pull
   requests.

Run it by hand from the Actions tab ("Run workflow"), optionally with a
version or `force`.

## License

MIT. See [LICENSE](LICENSE).
