<#
.SYNOPSIS
  Starts the Multilingual Bias Drift Benchmark web app on Windows.

.DESCRIPTION
  Order of preference:
    1. WSL (Ubuntu) if installed  -> runs scripts/start-wsl.sh inside WSL (recommended behind company proxies)
    2. uv with an installed Python (no Python download)
    3. installed Python + venv
  Docker users: docker compose up  (see docs/DEPLOY.md)

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\start.ps1
  powershell -ExecutionPolicy Bypass -File .\start.ps1 -Mode python -Port 8080
#>
param(
    [ValidateSet("auto", "wsl", "uv", "python")] [string]$Mode = "auto",
    [int]$Port = 8000
)

$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot
function Info($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "FEHLER: $msg" -ForegroundColor Red; exit 1 }

if (-not (Test-Path ".\pyproject.toml")) { Fail "pyproject.toml nicht gefunden. start.ps1 muss im Projektordner liegen." }
$env:MBDB_DEMO_DELAY_SECONDS = "0.15"

function Has-Wsl { try { $out = (wsl.exe -l -q 2>$null) -join ""; return ($LASTEXITCODE -eq 0 -and $out.Trim().Length -gt 0) } catch { return $false } }
function Find-Python {
    foreach ($candidate in @("py", "python")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -notmatch "WindowsApps") { return $candidate }
    }
    return $null
}

if ($Mode -eq "auto") {
    if (Has-Wsl) { $Mode = "wsl" }
    elseif ((Get-Command uv -ErrorAction SilentlyContinue) -and (Find-Python)) { $Mode = "uv" }
    elseif (Find-Python) { $Mode = "python" }
    else { Fail "Weder WSL noch Python gefunden. Optionen: WSL (wsl --install, Freigabe durch IT), Python 3.10+ aus dem Softwarecenter, oder Docker (docs/DEPLOY.md)." }
}

switch ($Mode) {
    "wsl" {
        Info "Starte in WSL (Ubuntu). Browser: http://localhost:$Port"
        $wslPath = (wsl.exe wslpath -a "$PSScriptRoot").Trim()
        wsl.exe bash -lc "set -e; mkdir -p ~/mbdb && rsync -a --delete --exclude .venv --exclude .git '$wslPath/' ~/mbdb/ 2>/dev/null || cp -r '$wslPath/.' ~/mbdb/; cd ~/mbdb && PORT=$Port bash scripts/start-wsl.sh"
    }
    "uv" {
        $env:UV_SYSTEM_CERTS = "true"              # company TLS inspection: use the Windows certificate store
        $env:UV_PYTHON_PREFERENCE = "only-system"   # never download Python (large downloads are often cut by proxies)
        Info "uv sync (nutzt installiertes Python) ..."
        uv sync --extra web
        if ($LASTEXITCODE -ne 0) { Fail "uv sync fehlgeschlagen. Alternativ: .\start.ps1 -Mode wsl  oder  -Mode python" }
        uv run fillblank-web --port $Port --open
    }
    "python" {
        $py = Find-Python
        if (-not $py) { Fail "Kein Python gefunden." }
        if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
            Info "Virtuelle Umgebung anlegen (.venv) ..."
            if ($py -eq "py") { py -3 -m venv .venv } else { python -m venv .venv }
        }
        Info "Paket installieren ..."
        & ".\.venv\Scripts\python.exe" -m pip install -e ".[web]" --use-feature=truststore
        if ($LASTEXITCODE -ne 0) { & ".\.venv\Scripts\python.exe" -m pip install -e ".[web]" }
        if ($LASTEXITCODE -ne 0) { Fail "pip install fehlgeschlagen. Siehe docs/WINDOWS_SETUP.md." }
        & ".\.venv\Scripts\fillblank-web.exe" --port $Port --open
    }
}
