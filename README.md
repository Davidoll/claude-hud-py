# claude-hud-py

A feature-rich **Claude Code status line** built in **pure Python 3** with
**zero third-party dependencies**. It shows the current AI model, context-window
usage, **live tool-call tracking** (e.g. how many Bash commands ran), **task
progress**, and **subagent info** - all cross-platform (Linux / macOS / Windows).

```
 ◆ GLM-5.2[1m] · projects · git:main✱ · 12m · $0.04 · 1 CLAUDE.md · 2 MCPs
   ctx ████████░░░░░░░░░░░░ 38% · 75K/200K ↑61K ↓14K · effort:high · ⚡fast
   ◐ Bash: npm test  ◐ Agent: 分析transcript · ✓ Read ×3 ✓ Edit ×2 ✓ Bash ×11
   ▸ 实现 hud.py 主脚本 (1/3) · ⊕ subagent ×2
```

## Why

[claude-hud-deepseek](https://github.com/anykeith/claude-hud-deepseek) is a great
Node.js status line, but it requires **Node.js ≥ 18**. On machines with an older
Node (or no Node at all) it won't run. This project re-implements the same idea -
**plus subagent tracking and cross-platform support** - in Python 3, which ships
on virtually every Linux/macOS/WSL/Windows dev box.

## How it works

Claude Code's `statusLine` stdin payload carries the model, context-window, cost,
effort, etc. - but **not** tool-call or subagent info. So this project uses a
classic hook + shared-state pattern:

1. **PreToolUse hook** (`hud.py --pre-tool`) - records each tool start into a
   per-session JSON file in the temp dir: `tools[name].n++` + `targets`.
2. **PostToolUse hook** (`hud.py --post-tool`) - records completion:
   `tools[name].n--`, moves the target into `recent` (last 5).
3. **statusLine** (`hud.py`) - reads that state file (falls back to parsing the
   transcript when the hook state is >5s stale) and also parses the transcript
   for completed-tool counts, task progress (`TaskCreate`/`TaskUpdate`), and
   subagent (`Agent`) stats. Renders a dynamic 2-4 line bar.

All three entry points live in a **single file** (`hud.py`) so install only
configures one script path.

## Requirements

- Python 3.6+ (`python3` on Linux/macOS, `python` on Windows)
- `git` (optional - only for the git segment)
- Claude Code with custom status-line + hooks support

## Install

```bash
cd claude-hud-py
python3 install.py      # Linux/macOS  (Windows: python install.py)
```

This:
- copies `hud.py` to `~/.claude/statusline-hud/hud.py`
- backs up `~/.claude/settings.json` to `settings.json.bak.<timestamp>`
- writes the `statusLine` entry **and** `PreToolUse`/`PostToolUse` hook groups
  (idempotent - re-running updates in place without duplicating)

Restart Claude Code (or wait for the next status tick) and the bar appears.
The hooks start recording tool calls immediately.

## Uninstall

```bash
python3 uninstall.py    # Windows: python uninstall.py
```

Removes the `statusLine` + our hook groups and the `~/.claude/statusline-hud/`
directory. Your other settings (env, permissions, mcpServers, other hooks) are
preserved; backups are kept.

## What it shows

| Line | Content (shown only when available) |
|---|---|
| 1 | model · working dir · `git:<branch>✱` · session duration · cost · config counts (CLAUDE.md / rules / MCPs / hooks) |
| 2 | context bar (color-coded) · `used/size ↑in ↓out` · `effort` · `thinking` · `⚡fast` |
| 3 | `◐` running tools (name + target, `×N`) · `✓` completed tools (name `×N`) |
| 4 | `▸` active task + `(done/total)` · `⊕` subagent count |

Every segment degrades gracefully - fields absent from the payload (common with
third-party backends that don't return Anthropic rate-limit headers) are simply
omitted.

### Color thresholds (context bar)

| usage | color |
|---|---|
| < 50% | green |
| 50–80% | yellow |
| ≥ 80% | red |

## Cross-platform notes

- The interpreter name is auto-detected: `python3` on Linux/macOS, `python` on
  Windows (where `python3` usually doesn't exist).
- `settings.json` command paths use **forward slashes** (Git Bash on Windows
  would otherwise eat backslashes).
- Temp/cache files use `tempfile.gettempdir()` - never a hardcoded `/tmp`.
- ANSI colors work in modern Windows Terminal / PowerShell; set `NO_COLOR=1` to
  disable color everywhere.

## Customize

Edit `~/.claude/statusline-hud/hud.py` (single file) and re-run `install.py`.
Common tweaks:

- **Bar width**: `BAR_WIDTH = 20`
- **Stale threshold** (hook state -> transcript fallback): `HOOK_STALE_MS = 5000`
- **Colors**: the `ANSI` block, or `NO_COLOR=1`
- **Segments**: `build()` builds `seg1` / `ctx_segs` / `l3_segs` / `l4_segs`
- **Tool target labels**: `extract_target()`
- **More stdin fields** (rate_limits, session_name, vim.mode...): see the
  [status-line docs](https://code.claude.com/docs/en/statusline)

## Test

```bash
python3 hud.py --test              # render against your latest real transcript
echo '{}' | python3 hud.py         # empty input (degraded)
# simulate a tool call through the hooks:
echo '{"tool_name":"Bash","tool_input":{"command":"ls"},"transcript_path":"/tmp/x.jsonl"}' | python3 hud.py --pre-tool
```

## Project layout

```
claude-hud-py/
├── hud.py          # statusLine + PreToolUse/PostToolUse hooks (single file)
├── install.py      # cross-platform installer
├── uninstall.py    # cross-platform uninstaller
└── README.md
```

## License

MIT
