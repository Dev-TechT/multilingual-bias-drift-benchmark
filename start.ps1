<#
.SYNOPSIS
  Starts the Multilingual Bias Drift Benchmark web app on Windows (no Docker needed).

.DESCRIPTION
  - Uses the Windows certificate store, so corporate TLS inspection ("invalid peer certificate: UnknownIssuer") does not break downloads.
  - Uses uv if installed (also installs Python if none is present), otherwise an installed Python (py / python).
  - Creates .venv inside this folder, installs the app and opens http://127.0.0.1:8000.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\start.ps1
  powershell -ExecutionPolicy Bypass -File .\start.ps1 -Port 8080 -Test
#>
param(
    [int]$Port = 8000,
    [switch]$Test,      # run the test suite before starting
    [switch]$NoBrowser,
    [switch]$NoUv       # ignore uv and use an installed Python instead
)

# "Continue": Windows PowerShell 5.1 would otherwise abort on harmless stderr output of native tools.
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

function Info($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "FEHLER: $msg" -ForegroundColor Red; exit 1 }

if (-not (Test-Path ".\pyproject.toml")) { Fail "pyproject.toml nicht gefunden. start.ps1 muss im Projektordner liegen (multilingual-bias-drift-benchmark-main)." }
if ($PSScriptRoot -match "OneDrive") {
    Write-Host "Hinweis: Der Ordner liegt in OneDrive. Die .venv mit tausenden Dateien wird dann mitsynchronisiert." -ForegroundColor Yellow
    Write-Host "         Besser: Ordner nach C:\dev kopieren und dort starten." -ForegroundColor Yellow
}

# Corporate proxies re-sign TLS traffic. Trust the Windows certificate store instead of bundled CAs.
$env:UV_NATIVE_TLS = "true"
$env:MBDB_DEMO_DELAY_SECONDS = "0.15"
$browserArg = if ($NoBrowser) { @() } else { @("--open") }

$uv = if ($NoUv) { $null } else { Get-Command uv -ErrorAction SilentlyContinue }
if ($uv) {
    Info "uv gefunden: $($uv.Source)"
    Info "Abhaengigkeiten installieren (uv sync) ..."
    uv sync --extra web --extra dev
    if ($LASTEXITCODE -ne 0) { Fail "uv sync fehlgeschlagen. Tipp: mit -NoUv ein installiertes Python verwenden. Details: docs/WINDOWS_SETUP.md" }
    if ($Test) {
        Info "Tests ausfuehren ..."
        uv run python -m pytest -q
        if ($LASTEXITCODE -ne 0) { Fail "Tests fehlgeschlagen." }
    }
    Info "Starte Web-App auf http://127.0.0.1:$Port  (Beenden mit Strg+C)"
    uv run fillblank-web --port $Port @browserArg
    exit $LASTEXITCODE
}

# Fallback: installed Python
$py = $null
foreach ($candidate in @("py", "python")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch "WindowsApps") { $py = $candidate; break }
}
if (-not $py) { Fail "Weder uv noch Python gefunden. Installiere Python 3.10+ (Softwarecenter/python.org) oder uv, dann erneut starten." }
Info "Python gefunden: $py"

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Info "Virtuelle Umgebung anlegen (.venv) ..."
    if ($py -eq "py") { py -3 -m venv .venv } else { python -m venv .venv }
}
$venvPy = ".\.venv\Scripts\python.exe"
Info "Paket installieren ..."
& $venvPy -m pip install -e ".[web,dev]" --use-feature=truststore
if ($LASTEXITCODE -ne 0) {
    Info "Zweiter Versuch ohne truststore-Flag ..."
    & $venvPy -m pip install -e ".[web,dev]"
    if ($LASTEXITCODE -ne 0) { Fail "pip install fehlgeschlagen. Siehe docs/WINDOWS_SETUP.md." }
}
if ($Test) {
    Info "Tests ausfuehren ..."
    & $venvPy -m pytest -q
    if ($LASTEXITCODE -ne 0) { Fail "Tests fehlgeschlagen." }
}
Info "Starte Web-App auf http://127.0.0.1:$Port  (Beenden mit Strg+C)"
& ".\.venv\Scripts\fillblank-web.exe" --port $Port @browserArg
