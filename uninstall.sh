#!/usr/bin/env bash
# Uninstall claude-hud-py: remove the statusLine setting and the script dir.
set -euo pipefail

SETTINGS="$HOME/.claude/settings.json"
DEST_DIR="$HOME/.claude/statusline-hud"

echo "==> Uninstalling claude-hud-py"

python3 - "$SETTINGS" <<'PY'
import json, os, sys
settings_path = sys.argv[1]
try:
    with open(settings_path) as f:
        cfg = json.load(f)
except Exception:
    cfg = {}
if isinstance(cfg, dict) and "statusLine" in cfg:
    del cfg["statusLine"]
    with open(settings_path, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("    removed statusLine from " + settings_path)
else:
    print("    no statusLine field found, nothing to remove")
PY

rm -rf "$DEST_DIR"
echo "    removed $DEST_DIR"
echo "==> Done. (Your settings.json backups are kept as settings.json.bak.*)"
