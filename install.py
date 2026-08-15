#!/usr/bin/env python3
"""Cross-platform installer for claude-hud-py (Linux / macOS / Windows).

Usage:
  python3 install.py      # on Linux/macOS
  python install.py       # on Windows

Copies hud.py to ~/.claude/statusline-hud/ and wires up the statusLine plus
PreToolUse/PostToolUse hooks in ~/.claude/settings.json (backed up first,
idempotent). Uses forward-slash paths and the right interpreter name per
platform so it works on Windows (Git Bash / PowerShell) too.
"""
import os
import sys
import json
import shutil
import platform
import datetime

HOME = os.path.expanduser("~")
DEST_DIR = os.path.join(HOME, ".claude", "statusline-hud")
DEST = os.path.join(DEST_DIR, "hud.py")
SETTINGS = os.path.join(HOME, ".claude", "settings.json")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(SCRIPT_DIR, "hud.py")


def find_python():
    """Interpreter command name for settings.json (Windows usually lacks python3)."""
    if platform.system() == "Windows":
        return "python"
    return "python3"


def is_our_group(g, dest_fwd):
    """Does this hook group belong to claude-hud-py (by command path match)?"""
    if not isinstance(g, dict):
        return False
    for h in g.get("hooks", []) or []:
        c = h.get("command", "") if isinstance(h, dict) else ""
        if dest_fwd in c:
            return True
    return False


def main():
    if not os.path.isfile(SRC):
        print(f"error: hud.py not found next to this installer ({SCRIPT_DIR})", file=sys.stderr)
        return 1
    py = find_python()
    print("==> Installing claude-hud-py")

    os.makedirs(DEST_DIR, exist_ok=True)
    shutil.copy2(SRC, DEST)
    try:
        os.chmod(DEST, 0o755)
    except Exception:
        pass
    print(f"    copied hud.py -> {DEST}")

    if os.path.isfile(SETTINGS):
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        shutil.copy2(SETTINGS, f"{SETTINGS}.bak.{ts}")
        print("    backed up settings.json")

    cfg = {}
    if os.path.isfile(SETTINGS):
        try:
            with open(SETTINGS, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict):
                cfg = {}
        except Exception:
            cfg = {}

    dest_fwd = DEST.replace(os.sep, "/")
    cmd = f"{py} {dest_fwd}"
    cfg["statusLine"] = {"type": "command", "command": cmd, "refreshInterval": 1}

    pre_group = {"matcher": "", "hooks": [{"type": "command", "command": f"{cmd} --pre-tool"}]}
    post_group = {"matcher": "", "hooks": [{"type": "command", "command": f"{cmd} --post-tool"}]}

    hooks = cfg.setdefault("hooks", {})

    def set_group(evt, group):
        arr = hooks.get(evt, [])
        if not isinstance(arr, list):
            arr = []
        arr = [g for g in arr if not is_our_group(g, dest_fwd)]
        arr.insert(0, group)
        hooks[evt] = arr

    set_group("PreToolUse", pre_group)
    set_group("PostToolUse", post_group)

    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    with open(SETTINGS, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"    configured statusLine + hooks -> {SETTINGS}")

    print("==> Done.")
    print(f"    Test:  {cmd} --test")
    print("    Reload: restart Claude Code, or it updates on the next status tick.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
