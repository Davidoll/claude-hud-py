#!/usr/bin/env python3
"""Claude Code status line HUD — pure Python, zero third-party deps.

Reads the session JSON that Claude Code pipes to stdin and prints a
two-line, ANSI-colored status bar:

  ◆ <model>  <dir>  git:<branch>✱  <duration>  <cost>
    ctx ████████░░░░░░░░░░ <pct>% · <used>/<size> ↑<in> ↓<out> · effort:<lvl> ⚡

Every field is optional: missing pieces are skipped so the bar degrades
gracefully (third-party backends often omit rate_limits / effort / etc).
"""

import sys
import os
import json
import re
import subprocess

# ---------------------------------------------------------------------------
# ANSI colors (respects the conventional NO_COLOR env var)
# ---------------------------------------------------------------------------
if os.environ.get("NO_COLOR"):
    RESET = DIM = BOLD = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = ""
else:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

BAR_WIDTH = 20
BAR_FULL = "█"
BAR_EMPTY = "░"


# ---------------------------------------------------------------------------
# formatting helpers
# ---------------------------------------------------------------------------
def fmt_tokens(n):
    """75000 -> '75K', 1500000 -> '1.5M', None -> '?'."""
    if n is None:
        return "?"
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "?"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n // 1000}K"
    return str(n)


def fmt_duration(ms):
    """milliseconds -> '12m' / '1h5m' / '42s'."""
    if not ms:
        return None
    try:
        s = int(ms) // 1000
    except (TypeError, ValueError):
        return None
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h:
        return f"{h}h{m}m"
    if m:
        return f"{m}m"
    return f"{s}s"


def fmt_cost(usd):
    if usd is None:
        return None
    try:
        usd = float(usd)
    except (TypeError, ValueError):
        return None
    return f"${usd:.2f}"


def pct_color(pct):
    if pct >= 80:
        return RED
    if pct >= 50:
        return YELLOW
    return GREEN


def render_bar(pct):
    pct = max(0, min(100, pct))
    filled = int(round(pct / 100 * BAR_WIDTH))
    return BAR_FULL * filled + BAR_EMPTY * (BAR_WIDTH - filled)


def join_segs(segs):
    """join non-empty segments with a dim middle-dot separator."""
    return f" {DIM}·{RESET} ".join(s for s in segs if s)


# ---------------------------------------------------------------------------
# git status (single call: branch name + dirty flag)
# ---------------------------------------------------------------------------
def git_info(cwd):
    """Return (branch, dirty) or None if not a git repo / git unavailable."""
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "status", "-b", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if out.returncode != 0 or not out.stdout:
        return None
    lines = out.stdout.splitlines()
    first = lines[0] if lines else ""
    m = re.match(r"## (\S+)", first)
    if not m:
        return None
    branch = m.group(1).split("...")[0]  # strip "...origin/main [ahead 1]"
    dirty = len(lines) > 1  # any line beyond the branch header = uncommitted
    return branch, dirty


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def build(data):
    """Build (line1, line2) from the parsed stdin JSON dict."""
    if not isinstance(data, dict):
        data = {}

    model = (data.get("model") or {}).get("display_name") or "Claude"
    workspace = data.get("workspace") or {}
    cwd = workspace.get("current_dir") or data.get("cwd") or os.getcwd()
    dirname = os.path.basename(cwd.rstrip("/")) or cwd

    cost = data.get("cost") or {}
    duration = fmt_duration(cost.get("total_duration_ms"))
    cost_str = fmt_cost(cost.get("total_cost_usd"))

    cw = data.get("context_window") or {}
    size = cw.get("context_window_size")
    in_tok = cw.get("total_input_tokens")
    out_tok = cw.get("total_output_tokens")
    pct = cw.get("used_percentage")
    if pct is None:
        # fall back to computing from token counts if the backend omits it
        used = (in_tok or 0) + (out_tok or 0)
        if size and used:
            pct = used / size * 100
        else:
            pct = 0
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        pct = 0.0
    pct_i = int(round(pct))

    effort = (data.get("effort") or {}).get("level")
    thinking = (data.get("thinking") or {}).get("enabled")
    fast = data.get("fast_mode")

    # --- line 1: model · dir · git · duration · cost ---
    seg1 = [f"{CYAN}{BOLD}◆ {model}{RESET}", f"{DIM}{dirname}{RESET}"]
    gi = git_info(cwd)
    if gi:
        branch, dirty = gi
        g = f"{MAGENTA}git:{branch}{RESET}"
        if dirty:
            g = f"{MAGENTA}git:{branch}{RED}✱{RESET}"
        seg1.append(g)
    if duration:
        seg1.append(f"{DIM}{duration}{RESET}")
    if cost_str:
        seg1.append(f"{GREEN}{cost_str}{RESET}")
    line1 = " " + join_segs(seg1)

    # --- line 2: ctx bar pct% · used/size ↑in ↓out · effort/thinking/fast ---
    col = pct_color(pct)
    used_tok = (in_tok or 0) + (out_tok or 0)
    ctx_segs = [f"{col}ctx {render_bar(pct)} {pct_i}%{RESET}"]
    if size:
        ctx_segs.append(
            f"{fmt_tokens(used_tok)}/{fmt_tokens(size)} "
            f"{DIM}↑{fmt_tokens(in_tok)} ↓{fmt_tokens(out_tok)}{RESET}"
        )
    flags = []
    if effort:
        flags.append(f"{YELLOW}effort:{effort}{RESET}")
    if thinking:
        flags.append(f"{BLUE}thinking{RESET}")
    if fast:
        flags.append(f"{YELLOW}⚡fast{RESET}")
    ctx_segs.extend(flags)
    line2 = "   " + join_segs(ctx_segs)

    return line1, line2


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------
def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        data = {}
    line1, line2 = build(data)
    sys.stdout.write(line1 + "\n" + line2 + "\n")


MOCK = {
    "model": {"id": "glm-5.2", "display_name": "GLM-5.2[1m]"},
    "workspace": {"current_dir": "/home/linlinger/projects"},
    "cost": {"total_cost_usd": 0.0421, "total_duration_ms": 742000},
    "context_window": {
        "used_percentage": 38.2,
        "context_window_size": 200000,
        "total_input_tokens": 61234,
        "total_output_tokens": 14389,
    },
    "effort": {"level": "high"},
    "fast_mode": True,
}


if __name__ == "__main__":
    if "--test" in sys.argv:
        line1, line2 = build(MOCK)
        sys.stdout.write(line1 + "\n" + line2 + "\n")
    else:
        main()
