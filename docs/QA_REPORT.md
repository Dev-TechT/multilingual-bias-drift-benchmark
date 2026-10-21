# QA report — v0.4.0

Date: 2026-10-21 · Linux, Python 3.12, FastAPI, headless Chromium.

| Gate | Result |
| --- | --- |
| New/updated test modules (providers, judges, runner, web, datasets, reference servers) | **82 passed** in the development tree. The repository's original v0.1 tests run in CI together with these. |
| Reference servers end-to-end over real HTTP (`my_ai_server.py` → `http-json`, `my_judge_server.py` → `http-judge`) | ok (test + manual) |
| Simulated Azure OpenAI, 360 cases, 6 workers, external judge | 360/360; HTTP 429 retried; Arabic content-filter block recorded as `refusal_void`; drift alert `core24-06-surgeon = high` (en/de stereotype, ar refused); no keys in artifacts |
| Browser: own AI + external judge with min confidence 0.6 (demo judge reports 0.5) | all 360 cells marked "?", "needs human review" card and filter correct, no JS errors |
| Provider roles in UI (judge-only / target-only) | correct |
| `scripts/start-wsl.sh` from a clean checkout | creates `.venv`, installs, `/api/ready` = ready |
| Rate limit (429 after limit), retention (keeps newest N), readiness, token auth, SSRF checks, upload validation | covered by tests |
| Dataset validation, duplicate check, leak scan, Python 3.10 syntax, JS syntax | ok |
| Hugging Face bundle script | produces Space README with `sdk: docker`, `app_port: 8000` |

## Not verified here

- Docker image build and GHCR/Hugging Face publishing (no Docker daemon; the CI builds the image, starts it and runs a demo run).
- `start.ps1` on real Windows.
- Real Azure OpenAI / Azure AI Foundry / GitHub Models / Ollama endpoints and the Jev API (not built in; relay must be implemented from the vendor docs).
- Language quality of translated rows (native review before go-live).
