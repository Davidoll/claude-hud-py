#!/usr/bin/env bash
# Install claude-hud-py: copy the script and wire up the statusLine setting.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/hud.py"
DEST_DIR="$HOME/.claude/statusline-hud"
DEST="$DEST_DIR/hud.py"
SETTINGS="$HOME/.claude/settings.json"

if [[ ! -f "$SRC" ]]; then
    echo "error: hud.py not found next to this script ($SCRIPT_DIR)" >&2
    exit 1
fi

echo "==> Installing claude-hud-py"

mkdir -p "$DEST_DIR"
cp "$SRC" "$DEST"
chmod +x "$DEST"
echo "    copied hud.py -> $DEST"

# Back up settings.json before touching it.
if [[ -f "$SETTINGS" ]]; then
    cp "$SETTINGS" "$SETTINGS.bak.$(date +%Y%m%d%H%M%S)"
    echo "    backed up settings.json"
fi

# Merge the statusLine field idempotently. Using python for safe JSON handling
# (settings.json may contain comments / unicode we don't want to corrupt).
python3 - "$DEST" "$SETTINGS" <<'PY'
import json, os, sys
dest, settings_path = sys.argv[1], sys.argv[2]
cfg = {}
if os.path.exists(settings_path):
    try:
        with open(settings_path) as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            cfg = {}
    except Exception:
        cfg = {}
cfg["statusLine"] = {"type": "command", "command": f"python3 {dest}"}
os.makedirs(os.path.dirname(settings_path), exist_ok=True)
with open(settings_path, "w") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("    configured statusLine -> " + settings_path)
PY

echo "==> Done."
echo "    Test render:  python3 \"$DEST\" --test"
echo "    Reload: restart Claude Code, or it updates on the next status tick."
