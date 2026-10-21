# Windows setup (step by step)

## 1. Put the project in a local folder (not OneDrive)

The Python environment (`.venv`) has thousands of files; inside OneDrive they would be synced. Copy the project to `C:\dev`:

```powershell
New-Item -ItemType Directory -Path C:\dev -Force | Out-Null
Copy-Item "$env:USERPROFILE\OneDrive - Friedhelm Loh Group\multilingual-bias-drift-benchmark-main" C:\dev\ -Recurse -Force
```

## 2. Unpack the update over it

Downloads from Copilot/Teams usually land in `Downloads`, not in your user folder — that is why `Expand-Archive .\…zip` said the path does not exist.

```powershell
Expand-Archive "$env:USERPROFILE\Downloads\multilingual-bias-drift-benchmark-v0.3.0-update.zip" -DestinationPath C:\dev -Force
cd C:\dev\multilingual-bias-drift-benchmark-main
```

The ZIP contains the folder `multilingual-bias-drift-benchmark-main`, so the files land in the right place and overwrite the old versions.

## 3. Start

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

The script installs everything into `.venv`, starts the app and opens http://127.0.0.1:8000. Add `-Test` to run the test suite first. Stop with `Ctrl+C`.

## Troubleshooting

| Message | Cause | Fix |
| --- | --- | --- |
| `invalid peer certificate: UnknownIssuer` | The company proxy re-signs HTTPS traffic; uv does not trust that certificate by default. | `start.ps1` sets `UV_NATIVE_TLS=true` (Windows certificate store). Manually: `$env:UV_NATIVE_TLS="true"` before any `uv` command. |
| uv still cannot download Python | GitHub downloads blocked by proxy | Install Python 3.12 via Software Center / python.org, then `.\start.ps1 -NoUv`. |
| `No pyproject.toml found` | Command run in the wrong folder | `cd C:\dev\multilingual-bias-drift-benchmark-main` first. |
| `pip … SSL: CERTIFICATE_VERIFY_FAILED` | Same proxy issue for pip | `start.ps1` uses `--use-feature=truststore`; ask IT for the proxy root certificate if it persists. |
| Script blocked (`running scripts is disabled`) | Execution policy | Use the `powershell -ExecutionPolicy Bypass -File .\start.ps1` form shown above. |
| Port 8000 in use | Another app | `.\start.ps1 -Port 8080` |
| `docker` not found / hangs | Docker Desktop not installed or not running | Not needed — use `start.ps1`. |

## Manual commands (if you prefer)

```powershell
$env:UV_NATIVE_TLS = "true"
uv sync --extra web --extra dev
uv run python -m pytest -q
uv run fillblank-web --open
```
