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
#   TYPESET_CLAUDE_VERSION  release to install, e.g. 0.2.0, or "main" for the
#                           development branch (default: the latest release)
#   TYPESET_CLAUDE_SOURCE   anything pip can install; overrides the version
#   TYPESET_CLAUDE_METHOD   "pipx" or "venv" (default: pipx if available)

set -euo pipefail

main() {
  local repo="https://github.com/lucjross/claude-code-typesetter"
  local source="${TYPESET_CLAUDE_SOURCE:-}"
  local version="${TYPESET_CLAUDE_VERSION:-latest}"
  local data_dir="${XDG_DATA_HOME:-$HOME/.local/share}/claude-code-typesetter"
  local bin_dir="$HOME/.local/bin"

  say() { printf '%s\n' "$*"; }
  die() { printf 'error: %s\n' "$*" >&2; exit 1; }

  case "$(uname -s)" in
    Linux) ;;
    *) die "only Linux is supported (on Windows, use WSL)" ;;
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

  if [ -z "$source" ]; then
    if [ "$version" = latest ]; then
      # /releases/latest redirects to /releases/tag/<tag>, or to /releases if
      # there are none yet.
      local url
      url="$(curl -fsSL -o /dev/null -w '%{url_effective}' "$repo/releases/latest")" ||
        die "couldn't reach GitHub to find the latest release"
      case "$url" in
        */releases/tag/*) version="${url##*/releases/tag/}" ;;
        *) say "No release found; installing the main branch."; version=main ;;
      esac
    fi
    case "$version" in
      main) source="$repo/archive/refs/heads/main.tar.gz" ;;
      *) version="v${version#v}"
         source="$repo/archive/refs/tags/$version.tar.gz"
         curl -fsLI -o /dev/null "$source" || die "no release $version (see $repo/releases)" ;;
    esac
    say "Installing claude-code-typesetter $version..."
  fi

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
