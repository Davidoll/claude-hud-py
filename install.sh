#!/bin/sh
# One-command installer for claude-hud-py (Linux / macOS).
#
# Usage (paste one line into a terminal):
#   curl -fsSL https://raw.githubusercontent.com/linlinger/claude-hud-py/main/install.sh | sh
#   wget -qO- https://raw.githubusercontent.com/linlinger/claude-hud-py/main/install.sh | sh
#
# What it does:
#   1. Ensures Python 3.7+ (installs it via the system package manager if missing).
#   2. Downloads hud.py / install.py / uninstall.py to a temp dir.
#   3. Runs install.py, which copies hud.py into ~/.claude/statusline-hud/ and
#      wires up the statusLine + PreToolUse/PostToolUse hooks in settings.json.
#
# It does NOT install Claude Code (a separate product). If `claude` is missing
# it warns; the official installer is: curl -fsSL https://claude.ai/install.sh | bash

set -e

BASE="https://raw.githubusercontent.com/linlinger/claude-hud-py/main"

info() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; }

# Respect NO_COLOR (same convention as hud.py).
if [ -n "${NO_COLOR:-}" ]; then
    info() { printf '==> %s\n' "$*"; }
    warn() { printf '!! %s\n' "$*"; }
    err()  { printf 'error: %s\n' "$*" >&2; }
fi

# --- download helper: prefer curl, fall back to wget ---
if command -v curl >/dev/null 2>&1; then
    fetch() { curl -fsSL "$1"; }
elif command -v wget >/dev/null 2>&1; then
    fetch() { wget -qO- "$1"; }
else
    err "curl or wget is required to download files. Install one and retry."
    exit 1
fi

# --- Python 3.7+ detection ---
have_python3() {
    command -v python3 >/dev/null 2>&1 &&
        python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)' >/dev/null 2>&1
}

OS_NAME=$(uname -s)

# Use sudo unless already root or no sudo is available (e.g. some containers).
SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
fi

install_python() {
    info "No usable Python 3.7+ found; installing it..."
    case "$OS_NAME" in
        Darwin)
            if command -v brew >/dev/null 2>&1; then
                brew install python3
            else
                warn "Triggering Xcode Command Line Tools install (a system dialog will appear)..."
                xcode-select --install
                err "Finish the Command Line Tools install, then re-run this script."
                exit 1
            fi
            ;;
        Linux)
            if command -v apt-get >/dev/null 2>&1; then
                $SUDO apt-get update && $SUDO apt-get install -y python3
            elif command -v dnf >/dev/null 2>&1; then
                $SUDO dnf install -y python3
            elif command -v yum >/dev/null 2>&1; then
                $SUDO yum install -y python3
            elif command -v pacman >/dev/null 2>&1; then
                $SUDO pacman -Sy --noconfirm python
            elif command -v zypper >/dev/null 2>&1; then
                $SUDO zypper --non-interactive install python3
            elif command -v apk >/dev/null 2>&1; then
                apk add --no-cache python3
            else
                err "Unrecognized Linux package manager. Install Python 3.7+ manually and retry."
                exit 1
            fi
            ;;
        *)
            err "Unsupported OS: $OS_NAME (only Linux and macOS are supported)."
            exit 1
            ;;
    esac
}

# --- main ---
info "Installing claude-hud-py"

if ! have_python3; then
    install_python
    if ! have_python3; then
        err "Python is still not usable after install. Check your PATH and retry."
        exit 1
    fi
fi
info "Python 3 ready: $(python3 --version 2>&1)"

if command -v claude >/dev/null 2>&1; then
    info "Claude Code detected"
else
    warn "Claude Code not found (no 'claude' on PATH)."
    warn "This HUD is a Claude Code status line; install Claude Code first:"
    warn "  curl -fsSL https://claude.ai/install.sh | bash"
fi

# Download the project files into a temp dir, run install.py, then clean up.
TMPD=$(mktemp -d)
trap 'rm -rf "$TMPD"' EXIT
info "Downloading project files..."
fetch "$BASE/hud.py"       > "$TMPD/hud.py"
fetch "$BASE/install.py"   > "$TMPD/install.py"
fetch "$BASE/uninstall.py" > "$TMPD/uninstall.py"

python3 "$TMPD/install.py"

# Keep uninstall.py next to hud.py so it can be removed later in one step.
cp "$TMPD/uninstall.py" "$HOME/.claude/statusline-hud/uninstall.py"

info "Done."
info "  Restart Claude Code (or wait for the next status tick) and the bar appears."
info "  Uninstall: python3 ~/.claude/statusline-hud/uninstall.py"
