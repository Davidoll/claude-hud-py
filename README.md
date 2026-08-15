# claude-hud-py

A feature-rich **Claude Code status line** built in **pure Python 3** with
**zero third-party dependencies**. It shows the current AI model, context-window
usage, **live tool-call tracking** (e.g. how many Bash commands ran), **task
progress**, and **subagent info** - all cross-platform (Linux / macOS / Windows).

```
 ◆ GLM-5.2[1m] · projects · 会话名 · git:main✱ · PR#42 · 12m · $0.04 +156 -23 · 1 CLAUDE.md · 2 MCPs
   ctx ████████░░░░░░░░░░░░ 38% · 75K/200K ↑61K ↓14K · ⤶cache 66% · 5h 24%(2h12m) · effort:high · ⚡fast
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

- Python 3.7+ (`python3` on Linux/macOS, `python` on Windows)
- `git` (optional - only for the git segment)
- Claude Code with custom status-line + hooks support

## Install

### One command (recommended)

Paste one line into a terminal - the installer ensures **Python 3.7+**, downloads
the project, and configures everything. You only need a network connection and a
terminal.

**Linux / macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/linlinger/claude-hud-py/main/install.sh | sh
```

(No `curl`? Use `wget -qO- https://raw.githubusercontent.com/linlinger/claude-hud-py/main/install.sh | sh`.)

**Windows (PowerShell):**

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; irm https://raw.githubusercontent.com/linlinger/claude-hud-py/main/install.ps1 | iex
```

(From `cmd.exe`, wrap the same command: `powershell -NoProfile -ExecutionPolicy Bypass -Command "..."`.)

The installer:
- ensures **Python 3.7+** (system package manager on Linux, Homebrew / Xcode CLT
  on macOS, winget on Windows)
- downloads `hud.py` / `install.py` / `uninstall.py` and runs `install.py`, which:
  - copies `hud.py` to `~/.claude/statusline-hud/hud.py`
  - backs up `~/.claude/settings.json` to `settings.json.bak.<timestamp>`
  - writes the `statusLine` entry (with `refreshInterval: 1` for live token
    updates) **and** `PreToolUse`/`PostToolUse` hook groups (idempotent -
    re-running updates in place without duplicating)
- copies `uninstall.py` next to `hud.py` for easy removal later

It does **not** install Claude Code - if `claude` isn't on your PATH it warns.
(Install it with `curl -fsSL https://claude.ai/install.sh | bash`, or
`irm https://claude.ai/install.ps1 | iex` on Windows.)

Restart Claude Code (or wait for the next status tick) and the bar appears.
The hooks start recording tool calls immediately.

### Manual

```bash
cd claude-hud-py
python3 install.py      # Linux/macOS  (Windows: python install.py)
```

## Uninstall

One command (if you installed via the one-liner above):

```bash
python3 ~/.claude/statusline-hud/uninstall.py                          # Linux/macOS
python %USERPROFILE%\.claude\statusline-hud\uninstall.py               # Windows
```

Manual (from a clone of the repo):

```bash
python3 uninstall.py    # Windows: python uninstall.py
```

Removes the `statusLine` + our hook groups and the `~/.claude/statusline-hud/`
directory. Your other settings (env, permissions, mcpServers, other hooks) are
preserved; backups are kept.

## What it shows

| Line | Content (shown only when available) |
|---|---|
| 1 | model · working dir · session name · `git:<branch>✱` · `PR#<n> <state>` · session duration · cost + `+added -removed` lines · config counts (CLAUDE.md / rules / MCPs / hooks) |
| 2 | context bar (color-coded) · `used/size ↑in ↓out` · `⤶cache <hit>%` · `5h`/`7d` rate limits + reset countdown (if the backend provides them) · `effort` · `thinking` · `⚡fast` |
| 3 | `◐` running tools (name + target, `×N`) · `✓` completed tools (name `×N`) |
| 4 | `▸` active task + `(done/total)` · `⊕` subagent count |

Every segment degrades gracefully - fields absent from the payload (common with
third-party backends that don't return Anthropic rate-limit headers) are simply
omitted.

The status line runs on a `refreshInterval` (1s), so token counts and the
cache-hit percentage update live during streaming responses instead of only
between messages.

> **No account balance.** The `statusLine` payload has no balance/credit field.
> Cost (`$X.XX`), rate-limit usage + reset countdown, and cache-hit rate are all
> shown; true billing balance would need an out-of-band API call (credentials +
> a network request every tick), which is intentionally out of scope here.

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
- Colors **adapt to the terminal background**: set `CLAUDE_HUD_BG=light` (or
  `dark`) explicitly, or rely on auto-detection from the `COLORFGBG` env var.
  On light backgrounds, secondary text uses dark grey instead of `dim` (which is
  near-invisible on white) and low-contrast colors are bolded. Default is dark.

## Customize

Edit `~/.claude/statusline-hud/hud.py` (single file) and re-run `install.py`.
Common tweaks:

- **Chinese labels**: set `CLAUDE_HUD_LANG=zh` before launching Claude Code to
  switch UI labels to Chinese (`ctx`→`上下文`, `effort`→`思考强度`,
  `subagent`→`子代理`, …). Default is English; data (model / dir / git / tool
  names) is never translated.

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
├── install.py      # cross-platform installer (the actual copy + settings.json)
├── install.sh      # one-command installer (Linux / macOS)
├── install.ps1     # one-command installer (Windows)
├── uninstall.py    # cross-platform uninstaller
└── README.md
```

## License

MIT
