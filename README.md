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

Requires Linux, Python 3.10+, and Claude Code (`claude`) on your
PATH. Tested with Claude Code <!-- claude-code-version -->2.1.316<!-- /claude-code-version -->;
new releases are checked daily (see [the release watch](.github/workflows/claude-code-watch.yml)). It opens in a Chrome, Chromium, Edge or Brave app window if one is
installed, otherwise in your default browser. Windows isn't supported
natively (it needs Unix pseudo-terminals); WSL should work.

```sh
curl -fsSL https://raw.githubusercontent.com/lucjross/claude-code-typesetter/main/install.sh | bash
```

It installs the [latest release](https://github.com/lucjross/claude-code-typesetter/releases);
set `TYPESET_CLAUDE_VERSION=0.1.0` (or `main`) to pick another.
`typeset-claude --version` shows the version, which includes the Claude Code
version it was tested with, e.g. `0.1.0+cc.2.1.310`.

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

## License

MIT. See [LICENSE](LICENSE).
