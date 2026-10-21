# Windows setup

Company networks often inspect HTTPS traffic and cut large downloads. That breaks Python downloads by `uv` ("UnknownIssuer", "os error 10054") and the Microsoft Store Python alias does not help. The reliable path is **WSL (Ubuntu)**, which already contains Python.

## Recommended: WSL

Check: `wsl -l -v` in PowerShell shows a distribution (e.g. Ubuntu). Then:

```powershell
wsl -d Ubuntu
```

```bash
git clone https://github.com/Dev-TechT/multilingual-bias-drift-benchmark.git ~/mbdb
cd ~/mbdb
bash scripts/start-wsl.sh
```

Open **http://localhost:8000** in the Windows browser. If `localhost` does not work, use the address from `hostname -I`.

Or from PowerShell in the project folder: `powershell -ExecutionPolicy Bypass -File .\start.ps1` (uses WSL automatically when present).

### If pip reports `CERTIFICATE_VERIFY_FAILED` in WSL

Export the Windows root certificates once (PowerShell):

```powershell
$out = "C:\dev\windows-roots.crt"
Get-ChildItem Cert:\LocalMachine\Root | ForEach-Object {
  "-----BEGIN CERTIFICATE-----"; [Convert]::ToBase64String($_.RawData, 'InsertLineBreaks'); "-----END CERTIFICATE-----"
} | Set-Content -Encoding ascii $out
```

and trust them in Ubuntu:

```bash
sudo cp /mnt/c/dev/windows-roots.crt /usr/local/share/ca-certificates/windows-roots.crt
sudo update-ca-certificates
```

`start-wsl.sh` then uses the system certificate store automatically.

## Alternatives

| Situation | Command |
| --- | --- |
| Python 3.10+ installed (Software Center / python.org) | `.\start.ps1 -Mode python` |
| uv + installed Python | `.\start.ps1 -Mode uv` (never downloads Python; uses `UV_SYSTEM_CERTS`) |
| Docker/Podman with licence | `docker run --rm -p 127.0.0.1:8000:8000 ghcr.io/dev-techt/multilingual-bias-drift-benchmark:latest` |

## Troubleshooting

| Message | Fix |
| --- | --- |
| `UV_NATIVE_TLS is deprecated` | harmless; current scripts use `UV_SYSTEM_CERTS` |
| `Failed to extract archive … os error 10054` (uv Python download) | proxy cuts the download → use WSL or an installed Python |
| `Python wurde nicht gefunden … Microsoft Store` | that is only the Store alias; install Python or use WSL |
| `No pyproject.toml found` | run commands inside the project folder |
| `ensurepip is not available` (WSL) | `sudo apt update && sudo apt install -y python3-venv` |
| Port 8000 in use | `PORT=8080 bash scripts/start-wsl.sh` or `.\start.ps1 -Port 8080` |
| Project in OneDrive | copy it to a local folder (`C:\dev` or WSL home); `.venv` has thousands of files |
