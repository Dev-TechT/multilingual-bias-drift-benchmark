#!/usr/bin/env bash
# Start the web app in WSL/Ubuntu (or any Linux/macOS) without Docker.
# Usage:  bash scripts/start-wsl.sh            -> http://localhost:8000
#         PORT=8080 bash scripts/start-wsl.sh
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$PWD" == /mnt/* ]]; then
  echo "Hint: the project is on the Windows drive ($PWD). Copy it to your Linux home for speed:  cp -r \"$PWD\" ~/mbdb && cd ~/mbdb"
fi
PY=${PYTHON:-python3}
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "Python 3.10+ required"; exit 1; }
if [[ ! -x .venv/bin/python ]]; then
  "$PY" -m venv .venv || { echo "Run: sudo apt update && sudo apt install -y python3-venv"; exit 1; }
fi
# Company proxies: trust the system certificate store if it has been extended (see docs/WINDOWS_SETUP.md).
[[ -f /etc/ssl/certs/ca-certificates.crt ]] && export PIP_CERT="${PIP_CERT:-/etc/ssl/certs/ca-certificates.crt}"
.venv/bin/pip install -q -e ".[web]"
export MBDB_DEMO_DELAY_SECONDS="${MBDB_DEMO_DELAY_SECONDS:-0.15}"
echo "Open http://localhost:${PORT:-8000} in your Windows browser (Ctrl+C to stop)."
exec .venv/bin/fillblank-web --host 0.0.0.0 --port "${PORT:-8000}"
