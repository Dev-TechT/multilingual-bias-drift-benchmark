# QA report — v0.3.0

Date: 2026-10-21 · Linux, Python 3.12, FastAPI 0.136, uv, headless Chromium.

| Gate | Result |
| --- | --- |
| Test suite | **107 passed** (incl. web API, live view, providers, judge, runner, datasets) |
| Fresh install via `uv sync --extra web --extra dev` from `uv.lock` (same path as `start.ps1`) | ok, all tests pass in the new `.venv`, entry points `fillblank-run` / `fillblank-web` present |
| Dataset validation (5 files, 522 rows) + JSON-Schema check of every row | ok |
| Duplicate check | 0 blocking errors |
| Leak scan | ok |
| Every translation group covers all 15 languages exactly once (27 groups) | ok |
| CLI: dry-run, output guard, readable missing-key error | ok |
| E2E against a simulated Azure OpenAI server, Core-24, 6 workers, LLM judge | 360/360 answers; 429 retried; Arabic content-filter block recorded as refusal; judge flagged German/English gender assumption the heuristic missed (2 disagreements); drift alert `core24-06-surgeon = high`; API key not in any artifact |
| Browser: live view mid-run (124/360 answers, grid partially filled, verdict "So far: …"), final view, validation banner, filters | ok, no JS errors (the one 422 in the console is the intentional missing-key test) |
| Python 3.10 syntax check | ok |

## Not verified here

- `start.ps1` on real Windows (no PowerShell in the sandbox). Logic mirrors the tested `uv sync` / `uv run` path; Windows PowerShell 5.1 pitfalls (stderr handling) were avoided deliberately.
- Docker build (no daemon; CI builds the image and checks `/api/health`).
- Real Azure / GitHub / Ollama endpoints (no credentials; protocol tested against a compatible fake server and unit tests).
- Language quality of the translation-assisted rows (native review before go-live).
