# One-command installer for claude-hud-py (Windows).
#
# Usage (paste into PowerShell):
#   [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; irm https://raw.githubusercontent.com/linlinger/claude-hud-py/main/install.ps1 | iex
# Or from cmd.exe:
#   powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; irm https://raw.githubusercontent.com/linlinger/claude-hud-py/main/install.ps1 | iex"
#
# What it does:
#   1. Ensures Python 3.7+ (installs it via winget if missing).
#   2. Downloads hud.py / install.py / uninstall.py to a temp dir.
#   3. Runs install.py, which copies hud.py into ~/.claude/statusline-hud/ and
#      wires up the statusLine + PreToolUse/PostToolUse hooks in settings.json.
#
# It does NOT install Claude Code (a separate product). If `claude` is missing
# it warns; the official installer is: irm https://claude.ai/install.ps1 | iex

$ErrorActionPreference = "Stop"

$BASE = "https://raw.githubusercontent.com/linlinger/claude-hud-py/main"

# PowerShell 5.1 may default to TLS 1.0; GitHub requires TLS 1.2.
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

function Info([string]$m) { Write-Host "==> $m" }
function Warn([string]$m) { Write-Host "!! $m" -ForegroundColor Yellow }
function Err([string]$m)  { Write-Host "error: $m" -ForegroundColor Red }

# Returns a command array that runs Python >= 3.7, or $null.
function Resolve-Python {
    foreach ($exe in @("python", "python3")) {
        if (Get-Command $exe -ErrorAction SilentlyContinue) {
            & $exe -c "import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return @($exe) }
        }
    }
    # The `py` launcher is on PATH immediately after a fresh install, before the
    # `python` entry is visible in a new shell.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { return @("py", "-3") }
    }
    return $null
}

function Install-Python {
    Info "No usable Python 3.7+ found; installing via winget..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    } else {
        Err "winget not found. Install Python 3.7+ from https://www.python.org/downloads/ (check 'Add to PATH'), then retry."
        exit 1
    }
}

function Download([string]$path, [string]$dest) {
    (New-Object System.Net.WebClient).DownloadFile("$BASE/$path", $dest)
}

# --- main ---
Info "Installing claude-hud-py"

$python = Resolve-Python
if (-not $python) {
    Install-Python
    $python = Resolve-Python
    if (-not $python) {
        Err "Python is still not usable after install. Open a new terminal (to refresh PATH) and retry."
        exit 1
    }
}
Info "Python 3 ready"

if (Get-Command claude -ErrorAction SilentlyContinue) {
    Info "Claude Code detected"
} else {
    Warn "Claude Code not found (no 'claude' on PATH)."
    Warn "This HUD is a Claude Code status line; install Claude Code first:"
    Warn "  irm https://claude.ai/install.ps1 | iex"
}

# Download the project files into a temp dir, run install.py, then clean up.
$tmp = Join-Path $env:TEMP ("claude-hud-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    Info "Downloading project files..."
    Download "hud.py"       (Join-Path $tmp "hud.py")
    Download "install.py"   (Join-Path $tmp "install.py")
    Download "uninstall.py" (Join-Path $tmp "uninstall.py")

    & $python (Join-Path $tmp "install.py")
    if ($LASTEXITCODE -ne 0) { throw "install.py failed with exit code $LASTEXITCODE" }

    # Keep uninstall.py next to hud.py so it can be removed later in one step.
    Copy-Item (Join-Path $tmp "uninstall.py") (Join-Path $env:USERPROFILE ".claude\statusline-hud\uninstall.py") -Force
}
finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}

Info "Done."
Info "  Restart Claude Code (or wait for the next status tick) and the bar appears."
Info "  Uninstall: python $env:USERPROFILE\.claude\statusline-hud\uninstall.py"
