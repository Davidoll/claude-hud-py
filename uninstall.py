#!/usr/bin/env python3
"""Uninstall claude-hud-py: remove statusLine + hooks + script dir.

Usage:
  python3 uninstall.py   # Linux/macOS
  python uninstall.py    # Windows
"""
import os
import sys
import json
import shutil

HOME = os.path.expanduser("~")
SETTINGS = os.path.join(HOME, ".claude", "settings.json")
DEST_DIR = os.path.join(HOME, ".claude", "statusline-hud")


def is_our_group(g):
    if not isinstance(g, dict):
        return False
    dest_fwd = (DEST_DIR + "/").replace(os.sep, "/")
    for h in g.get("hooks", []) or []:
        c = h.get("command", "") if isinstance(h, dict) else ""
        if dest_fwd in c.replace(os.sep, "/"):
            return True
    return False


def main():
    print("==> Uninstalling claude-hud-py")
    try:
        with open(SETTINGS, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

    changed = False
    if isinstance(cfg, dict):
        if "statusLine" in cfg:
            del cfg["statusLine"]
            changed = True
        hooks = cfg.get("hooks")
        if isinstance(hooks, dict):
            for evt in list(hooks.keys()):
                arr = hooks.get(evt, [])
                if not isinstance(arr, list):
                    continue
                kept = [g for g in arr if not is_our_group(g)]
                if len(kept) != len(arr):
                    if kept:
                        hooks[evt] = kept
                    else:
                        del hooks[evt]
                    changed = True
        if changed:
            with open(SETTINGS, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
                f.write("\n")
            print(f"    removed statusLine + hooks from {SETTINGS}")
        else:
            print("    nothing to remove in settings.json")

    if os.path.isdir(DEST_DIR):
        shutil.rmtree(DEST_DIR)
        print(f"    removed {DEST_DIR}")

    print("==> Done. (settings.json backups kept as settings.json.bak.*)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
