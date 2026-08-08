#!/usr/bin/env python3
"""Claude Code HUD - pure Python 3, zero third-party dependencies.

Single file with multiple entry points:
  python3 hud.py             -> statusLine (reads session JSON on stdin)
  python3 hud.py --pre-tool  -> PreToolUse hook (track tool start)
  python3 hud.py --post-tool -> PostToolUse hook (track tool end)
  python3 hud.py --test      -> render with the latest real transcript

Architecture: PreToolUse/PostToolUse hooks write a shared JSON state file
(per session, keyed by transcript stem) tracking running tools and recent
completions. The statusLine reads that file (falling back to transcript
parsing when stale) and also parses the transcript for completed-tool
counts, task progress, and subagent info.

Cross-platform: uses os.path / tempfile / pathlib only; no hardcoded /tmp.
"""

import sys
import os
import json
import re
import glob
import subprocess
import tempfile
import time

# ---------------------------------------------------------------------------
# paths & constants
# ---------------------------------------------------------------------------
HOME = os.path.expanduser("~")
TRANSCRIPT_DIR = os.path.realpath(os.path.join(HOME, ".claude", "projects"))
SETTINGS_PATH = os.path.join(HOME, ".claude", "settings.json")
RULES_DIR = os.path.join(HOME, ".claude", "rules", "common")
CLAUDE_MD_HOME = os.path.join(HOME, ".claude", "CLAUDE.md")

MAX_TRANSCRIPT_BYTES = 5 * 1024 * 1024
MAX_TRANSCRIPT_LINES = 2000
HOOK_STALE_MS = 5000
RECENT_VISIBLE_MS = 3000
BAR_WIDTH = 20
BAR_FULL = "█"
BAR_EMPTY = "░"

# ---------------------------------------------------------------------------
# ANSI colors (respects NO_COLOR)
# ---------------------------------------------------------------------------
if os.environ.get("NO_COLOR"):
    RESET = DIM = BOLD = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = ""
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
    WHITE = "\033[37m"

ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def strip_ansi(s):
    return ANSI_RE.sub("", s) if isinstance(s, str) else ""


def safe_string(s, maxlen=4096):
    if not isinstance(s, str):
        return ""
    return s[:maxlen]


# ---------------------------------------------------------------------------
# formatting helpers
# ---------------------------------------------------------------------------
def fmt_tokens(n):
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
    return f" {DIM}·{RESET} ".join(s for s in segs if s)


def now_ms():
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# shared state file (hooks <-> statusline), cross-platform temp dir
# ---------------------------------------------------------------------------
def state_file(transcript_path):
    if not transcript_path:
        return os.path.join(tempfile.gettempdir(), "claude-hud-tools.json")
    stem = os.path.splitext(os.path.basename(transcript_path))[0]
    return os.path.join(tempfile.gettempdir(), f"claude-hud-tools-{stem}.json")


def read_state(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"tools": {}, "updated": 0}
        return data
    except Exception:
        return {"tools": {}, "updated": 0}


def write_state(path, state):
    """Atomic write via temp file + os.replace; never raises."""
    try:
        d = os.path.dirname(path) or "."
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".hud-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# extract a short target label for a tool call
# ---------------------------------------------------------------------------
def extract_target(name, inp):
    if not isinstance(inp, dict):
        return ""
    if name in ("Read", "Write", "Edit", "NotebookEdit"):
        p = strip_ansi(inp.get("file_path") or inp.get("path") or "")
        return os.path.basename(p) if p else ""
    if name == "Bash":
        cmd = strip_ansi(inp.get("command", ""))
        return (cmd[:27] + "...") if len(cmd) > 30 else cmd
    if name in ("Glob", "Grep"):
        return strip_ansi(inp.get("pattern", ""))[:30]
    if name == "Skill":
        return strip_ansi(inp.get("skill", ""))[:30]
    if name in ("Agent", "Task"):
        return strip_ansi(inp.get("description", ""))[:30]
    if name == "WebFetch":
        return strip_ansi(inp.get("url", ""))[:30]
    if name == "WebSearch":
        return strip_ansi(inp.get("query", ""))[:30]
    return ""


# ---------------------------------------------------------------------------
# hooks: track tool start / end into the shared state file
# ---------------------------------------------------------------------------
def hook_pre():
    try:
        raw = sys.stdin.buffer.read()
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return
        name = data.get("tool_name")
        if not name:
            return
        target = extract_target(name, data.get("tool_input") or {})
        path = state_file(data.get("transcript_path"))
        state = read_state(path)
        tools = state.setdefault("tools", {})
        entry = tools.get(name)
        if not isinstance(entry, dict):
            entry = {"n": entry if isinstance(entry, int) else 0,
                     "targets": [], "recent": []}
        entry["n"] = entry.get("n", 0) + 1
        if target:
            entry.setdefault("targets", []).append(target)
        entry.setdefault("recent", [])
        tools[name] = entry
        state["updated"] = now_ms()
        write_state(path, state)
    except Exception:
        pass


def hook_post():
    try:
        raw = sys.stdin.buffer.read()
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return
        name = data.get("tool_name")
        if not name:
            return
        path = state_file(data.get("transcript_path"))
        state = read_state(path)
        tools = state.get("tools", {})
        entry = tools.get(name)
        if entry is None:
            return
        if isinstance(entry, int):  # legacy bare-number format
            if entry <= 1:
                tools.pop(name, None)
            else:
                tools[name] = entry - 1
            state["updated"] = now_ms()
            write_state(path, state)
            return
        if not isinstance(entry, dict):
            return
        n = entry.get("n", 0)
        if n <= 0:
            return
        entry["n"] = n - 1
        targets = entry.get("targets", [])
        done = targets.pop(0) if targets else ""
        if done:
            recent = entry.setdefault("recent", [])
            recent.append({"target": done, "at": now_ms()})
            if len(recent) > 5:
                entry["recent"] = recent[-5:]
        if entry.get("n", 0) == 0:
            entry["targets"] = []
        tools[name] = entry
        state["updated"] = now_ms()
        write_state(path, state)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# read hook state (statusline side)
# ---------------------------------------------------------------------------
def read_hook_state(path):
    if not os.path.exists(path):
        return None
    state = read_state(path)
    updated = state.get("updated", 0)
    if updated and (now_ms() - updated) > HOOK_STALE_MS:
        return None
    tools = state.get("tools", {})
    if not tools:
        return None
    running = []
    recent = {}
    for name, v in tools.items():
        entry = v if isinstance(v, dict) else {"n": v or 0, "targets": [], "recent": []}
        if entry.get("n", 0) > 0:
            tgts = entry.get("targets", [])
            running.append({"name": name, "n": entry["n"],
                            "target": tgts[-1] if tgts else ""})
        for r in entry.get("recent", []):
            at = r.get("at", 0)
            if at and (now_ms() - at) < RECENT_VISIBLE_MS:
                recent[name] = recent.get(name, 0) + 1
    return {"running": running or None, "recent": recent or None}


# ---------------------------------------------------------------------------
# transcript parsing (sandboxed, size/line capped)
# ---------------------------------------------------------------------------
def sanitize_transcript_path(p):
    p = safe_string(p)
    if not p:
        return ""
    try:
        rp = os.path.realpath(p)
    except Exception:
        return ""
    if rp != TRANSCRIPT_DIR and not rp.startswith(TRANSCRIPT_DIR + os.sep):
        return ""
    return rp


def parse_transcript(path):
    empty = {"running": [], "completed": {}, "active_task": None,
             "agent_total": 0, "agent_running": 0}
    if not path:
        return empty
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > MAX_TRANSCRIPT_BYTES:
            return empty
    except Exception:
        return empty

    tool_map = {}      # tool_use_id -> {name, target, status}
    completed = {}     # name -> count
    tasks = {}         # taskId -> {subject, activeForm, status}
    order = []         # task creation order
    active_task = None
    agent_total = 0
    agent_running = 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= MAX_TRANSCRIPT_LINES:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                msg = rec.get("message")
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                rtype = rec.get("type")
                if rtype == "assistant":
                    for b in content:
                        if not isinstance(b, dict) or b.get("type") != "tool_use":
                            continue
                        bid = b.get("id")
                        bname = b.get("name")
                        binp = b.get("input") or {}
                        if bid and bname:
                            tool_map[bid] = {"name": bname,
                                             "target": extract_target(bname, binp),
                                             "status": "running"}
                        if bname == "TodoWrite" and isinstance(binp.get("todos"), list):
                            todos = binp["todos"]
                            act = next((t for t in todos if t.get("status") == "in_progress"), None)
                            if act:
                                done = sum(1 for t in todos if t.get("status") == "completed")
                                active_task = {
                                    "subject": act.get("content") or act.get("activeForm") or "",
                                    "done": done, "total": len(todos)}
                            else:
                                active_task = None
                        elif bname == "TaskCreate":
                            tid = str(len(order) + 1)
                            tasks[tid] = {"subject": binp.get("subject", ""),
                                          "activeForm": binp.get("activeForm", ""),
                                          "status": "pending"}
                            order.append(tid)
                        elif bname == "TaskUpdate":
                            tid = str(binp.get("taskId", ""))
                            if tid in tasks and binp.get("status"):
                                tasks[tid]["status"] = binp["status"]
                        elif bname == "Agent":
                            agent_total += 1
                            agent_running += 1
                elif rtype == "user":
                    for b in content:
                        if not isinstance(b, dict) or b.get("type") != "tool_result":
                            continue
                        tuid = b.get("tool_use_id")
                        tool = tool_map.get(tuid)
                        if tool:
                            is_err = b.get("is_error")
                            tool["status"] = "error" if is_err else "completed"
                            if not is_err:
                                completed[tool["name"]] = completed.get(tool["name"], 0) + 1
                            if tool["name"] == "Agent":
                                agent_running = max(0, agent_running - 1)
    except Exception:
        pass

    # derive active task from TaskCreate/TaskUpdate replay
    if not active_task and tasks:
        in_prog = [tasks[t] for t in order if tasks[t].get("status") == "in_progress"]
        if in_prog:
            t0 = in_prog[0]
            done = sum(1 for t in order if tasks[t].get("status") == "completed")
            active_task = {"subject": t0.get("subject") or t0.get("activeForm") or "",
                           "done": done, "total": len(order)}

    running = [v for v in tool_map.values() if v.get("status") == "running"]
    return {"running": running, "completed": completed, "active_task": active_task,
            "agent_total": agent_total, "agent_running": agent_running}


# ---------------------------------------------------------------------------
# git status & config counts
# ---------------------------------------------------------------------------
def get_git(cwd):
    if not cwd:
        return None
    try:
        r = subprocess.run(["git", "-C", cwd, "branch", "--show-current"],
                           capture_output=True, text=True, timeout=2)
        branch = r.stdout.strip()
        if not branch:
            return None
        s = subprocess.run(["git", "-C", cwd, "status", "--porcelain"],
                           capture_output=True, text=True, timeout=2)
        return {"branch": strip_ansi(branch), "dirty": bool(s.stdout.strip())}
    except Exception:
        return None


def get_config_counts(cwd):
    counts = {"claudeMd": 0, "rules": 0, "mcps": 0, "hooks": 0}
    try:
        if cwd and os.path.isfile(os.path.join(cwd, "CLAUDE.md")):
            counts["claudeMd"] += 1
        if os.path.isfile(CLAUDE_MD_HOME):
            counts["claudeMd"] += 1
    except Exception:
        pass
    try:
        if os.path.isdir(RULES_DIR):
            counts["rules"] = sum(1 for f in os.listdir(RULES_DIR) if f.endswith(".md"))
    except Exception:
        pass
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            s = json.load(f)
        counts["mcps"] = len(s.get("mcpServers") or {})
        hooks = s.get("hooks") or {}
        total = 0
        for phase in hooks.values():
            if isinstance(phase, list):
                for g in phase:
                    if isinstance(g, dict):
                        total += len(g.get("hooks") or [])
        counts["hooks"] = total
    except Exception:
        pass
    return counts


# ---------------------------------------------------------------------------
# build / render (dynamic 2-4 lines)
# ---------------------------------------------------------------------------
def build(data):
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
        used = (in_tok or 0) + (out_tok or 0)
        pct = (used / size * 100) if size and used else 0
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        pct = 0.0
    pct_i = int(round(pct))
    effort = (data.get("effort") or {}).get("level")
    thinking = (data.get("thinking") or {}).get("enabled")
    fast = data.get("fast_mode")

    # data sources
    tpath = sanitize_transcript_path(data.get("transcript_path", ""))
    hook = read_hook_state(state_file(data.get("transcript_path")))
    tdata = parse_transcript(tpath)
    git = get_git(cwd)
    config = get_config_counts(cwd)

    # running tools: hook state first, transcript fallback
    running = []
    if hook and hook.get("running"):
        running = hook["running"]
    else:
        for t in tdata["running"]:
            running.append({"name": t["name"], "n": 1, "target": t.get("target", "")})

    # completed: transcript counts + hook recent
    completed = dict(tdata["completed"])
    if hook and hook.get("recent"):
        for name, cnt in hook["recent"].items():
            completed[name] = completed.get(name, 0) + cnt

    active_task = tdata["active_task"]
    agent_total = tdata["agent_total"]
    agent_running = tdata["agent_running"]

    # --- line 1: model · dir · git · dur · cost · configs ---
    seg1 = [f"{CYAN}{BOLD}◆ {strip_ansi(model)}{RESET}", f"{DIM}{strip_ansi(dirname)}{RESET}"]
    if git:
        if git["dirty"]:
            seg1.append(f"{MAGENTA}git:{git['branch']}{RED}✱{RESET}")
        else:
            seg1.append(f"{MAGENTA}git:{git['branch']}{RESET}")
    if duration:
        seg1.append(f"{DIM}{duration}{RESET}")
    if cost_str:
        seg1.append(f"{GREEN}{cost_str}{RESET}")
    cfg_segs = []
    if config["claudeMd"]:
        cfg_segs.append(f"{config['claudeMd']} CLAUDE.md")
    if config["rules"]:
        cfg_segs.append(f"{config['rules']} rules")
    if config["mcps"]:
        cfg_segs.append(f"{config['mcps']} MCPs")
    if config["hooks"]:
        cfg_segs.append(f"{config['hooks']} hooks")
    if cfg_segs:
        seg1.append(f"{DIM}{' · '.join(cfg_segs)}{RESET}")
    line1 = " " + join_segs(seg1)

    # --- line 2: ctx bar pct · tokens · effort/thinking/fast ---
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

    # --- line 3: running + completed (only if any) ---
    l3_segs = []
    if running:
        items = []
        for r in running:
            label = f"{r['name']}: {r['target']}" if r.get("target") else r["name"]
            if r.get("n", 1) > 1:
                label += f" ×{r['n']}"
            items.append(strip_ansi(label))
        l3_segs.append(f"{YELLOW}◐{RESET} {CYAN}{'  '.join(items)}{RESET}")
    if completed:
        items = []
        for name, n in completed.items():
            label = f"{name}" + (f" ×{n}" if n > 1 else "")
            items.append(f"{DIM}✓{RESET} {strip_ansi(label)}")
        l3_segs.append("  ".join(items))

    # --- line 4: active task + subagent (only if any) ---
    l4_segs = []
    if active_task and active_task.get("subject"):
        prog = f" ({active_task['done']}/{active_task['total']})" if active_task.get("total", 0) > 0 else ""
        l4_segs.append(f"{YELLOW}▸{RESET} {strip_ansi(active_task['subject'])}{DIM}{prog}{RESET}")
    if agent_total > 0:
        if agent_running > 0:
            agent_label = f"subagent {agent_running} running/×{agent_total}"
        else:
            agent_label = f"subagent ×{agent_total}"
        l4_segs.append(f"{BLUE}⊕{RESET} {DIM}{agent_label}{RESET}")

    lines = [line1, line2]
    if l3_segs:
        lines.append("   " + join_segs(l3_segs))
    if l4_segs:
        lines.append("   " + join_segs(l4_segs))
    return lines


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------
def find_latest_transcript():
    try:
        files = glob.glob(os.path.join(TRANSCRIPT_DIR, "*", "*.jsonl"))
        if not files:
            return None
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return files[0]
    except Exception:
        return None


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    sys.stdout.write("\n".join(build(data)) + "\n")


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
    args = sys.argv[1:]
    if "--pre-tool" in args:
        hook_pre()
    elif "--post-tool" in args:
        hook_post()
    elif "--test" in args:
        tpath = find_latest_transcript()
        if tpath:
            MOCK["transcript_path"] = tpath
        sys.stdout.write("\n".join(build(MOCK)) + "\n")
    else:
        main()
