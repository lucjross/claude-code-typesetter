#!/usr/bin/env bash
# Install or update typeset-claude (claude-code-typesetter).
#
#   curl -fsSL https://raw.githubusercontent.com/lucjross/claude-code-typesetter/main/install.sh | bash
#
# Uses pipx if it's installed. Otherwise installs into its own virtualenv in
# ~/.local/share/claude-code-typesetter and links the command into
# ~/.local/bin. Re-run to update. Uninstall: `pipx uninstall
# claude-code-typesetter`, or delete those two paths.
#
# Environment overrides:
#   TYPESET_CLAUDE_SOURCE  what to install (default: the main branch archive)
#   TYPESET_CLAUDE_METHOD  "pipx" or "venv" (default: pipx if available)

set -euo pipefail

main() {
  local source="${TYPESET_CLAUDE_SOURCE:-https://github.com/lucjross/claude-code-typesetter/archive/refs/heads/main.tar.gz}"
  local data_dir="${XDG_DATA_HOME:-$HOME/.local/share}/claude-code-typesetter"
  local bin_dir="$HOME/.local/bin"

  say() { printf '%s\n' "$*"; }
  die() { printf 'error: %s\n' "$*" >&2; exit 1; }

  case "$(uname -s)" in
    Linux | Darwin) ;;
    *) die "only Linux and macOS are supported (on Windows, use WSL)" ;;
  esac

  local python=""
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
      python="$candidate"
      break
    fi
  done
  [ -n "$python" ] || die "Python 3.10 or newer is required"

  local method="${TYPESET_CLAUDE_METHOD:-}"
  if [ -z "$method" ]; then
    if command -v pipx >/dev/null 2>&1; then method=pipx; else method=venv; fi
  fi

  case "$method" in
    pipx)
      say "Installing with pipx..."
      pipx install --force "$source"
      ;;
    venv)
      say "Installing into $data_dir..."
      "$python" -m venv "$data_dir/venv"
      "$data_dir/venv/bin/python" -m pip install --quiet --upgrade pip
      "$data_dir/venv/bin/python" -m pip install --quiet --upgrade --force-reinstall "$source"
      mkdir -p "$bin_dir"
      ln -sf "$data_dir/venv/bin/typeset-claude" "$bin_dir/typeset-claude"
      case ":$PATH:" in
        *":$bin_dir:"*) ;;
        *) say "Note: $bin_dir is not on your PATH. Add this to your shell profile:"
           say "  export PATH=\"$bin_dir:\$PATH\"" ;;
      esac
      ;;
    *) die "TYPESET_CLAUDE_METHOD must be pipx or venv" ;;
  esac

  if ! command -v claude >/dev/null 2>&1; then
    say "Note: Claude Code (claude) isn't on your PATH yet; typeset-claude needs it."
  fi
  say "Done. Run typeset-claude in a project directory."
}

# Everything above is a function, so a partially downloaded script does nothing.
main "$@"
