# claude-hud-py

A lightweight **Claude Code status line** that shows the current AI model and
context-window usage — built in **pure Python 3**, with **zero third-party
dependencies**.

```
 ◆ GLM-5.2[1m]  ·  projects  ·  git:main✱  ·  12m  ·  $0.04
   ctx ████████░░░░░░░░░░░░ 38%  ·  75K/200K  ↑61K ↓14K  ·  effort:high  ·  ⚡fast
```

## Why

[claude-hud-deepseek](https://github.com/anykeith/claude-hud-deepseek) is great,
but it requires **Node.js ≥ 18**. On machines with an older Node (or no Node at
all) it won't run. This project re-implements the same idea in Python 3, which
ships on virtually every Linux/macOS/WSL dev box out of the box.

It is also **much simpler**: Claude Code already delivers the `context_window`
data (used %, token counts, window size) directly in the status-line stdin
payload, so the original project's transcript parsing + PreToolUse/PostToolUse
hook machinery is unnecessary here.

## Requirements

- Python 3.6+ (`python3`)
- `git` (optional — only for the git segment)
- Claude Code with custom status-line support

## Install

```bash
cd claude-hud-py
chmod +x install.sh
./install.sh
```

This copies `hud.py` to `~/.claude/statusline-hud/hud.py` and adds a
`statusLine` entry to `~/.claude/settings.json` (your original file is backed up
to `settings.json.bak.<timestamp>` first). Restart Claude Code (or wait for the
next status tick) and the bar appears.

## Uninstall

```bash
./uninstall.sh
```

Removes the `statusLine` setting and the `~/.claude/statusline-hud/` directory.

## What it shows

**Line 1** — model · working dir · git branch (✱ when dirty) · session duration · cost
**Line 2** — context progress bar (color-coded by usage) · `used/size` with in/out
tokens · `effort` · `thinking` · `⚡fast`

Every segment is optional. Fields absent from the payload (common with
third-party backends that don't return Anthropic rate-limit headers) are simply
omitted — the bar degrades gracefully instead of breaking.

### Color thresholds

| Context usage | Color |
|---|---|
| < 50% | green |
| 50–80% | yellow |
| ≥ 80% | red |

## Customize

Edit `~/.claude/statusline-hud/hud.py` and re-run `install.sh` (or just edit in
place — it's a single file). Common tweaks:

- **Bar width**: change `BAR_WIDTH = 20`.
- **Colors**: the `ANSI` block at the top, or set the `NO_COLOR=1` env var to
  disable color entirely.
- **Segments**: add/remove entries in the `seg1` / `ctx_segs` lists in `build()`.
- **Fields**: see Claude Code's
  [status-line docs](https://code.claude.com/docs/en/statusline) for the full
  stdin schema — e.g. add `rate_limits`, `session_name`, `vim.mode`, etc.

## Test

```bash
python3 hud.py --test              # built-in mock payload
echo '{}' | python3 hud.py         # empty input (degraded)
echo '{...}' | python3 hud.py      # your own JSON
```

## License

MIT
