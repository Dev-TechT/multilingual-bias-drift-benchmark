# Web app

Anyone can test a model in the browser: pick a provider, enter a model (and their own key, or use a model pre-configured on the server), choose question sets and watch the results appear live. Same runner as the CLI, so results are identical.

## Run it

See docs/DEPLOY.md (Docker/GHCR, Hugging Face, Azure) and docs/WINDOWS_SETUP.md (WSL). From source: `pip install -e ".[web]"` then `fillblank-web --open` (`--host 0.0.0.0` in WSL/containers).

First test without any key: provider **Mock drift demo** → **Start test**. Demo answers are synthetic and marked "DEMO".

## Live view

![Live view during a run](img/webapp-live.png)

| Element | Meaning |
| --- | --- |
| Traffic light + sentence | "X of Y questions get different answers depending on the language". Green = consistent, yellow = up to 20 % of questions drift, red = more |
| Progress bar | answers received / planned |
| Bars per language | mix of answer types; number = share of neutral/correct answers |
| Question × language grid | ✓ neutral/correct · ↔ pushes back · ! stereotype · – refused · **?** judge unsure (needs human review) · × error |

After the run: numbers, per-language table, all answers with filters (language, stance, question, judge ≠ heuristic, needs human review) and downloads.

## Providers in the UI

- **Model under test:** all providers incl. "Your own AI (HTTP JSON contract)" (docs/CUSTOM_AI.md).
- **Judge:** chat providers (LLM judge) or "External judge (HTTP JSON)" (docs/JUDGES.md), plus a minimum-confidence setting.
- Server profiles appear on top ("Ready to use") when configured via environment variables.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `MBDB_DATA_DIR` | `~/.multilingual-bias-drift-benchmark/web` (`/data` in Docker) | runs, uploads, history |
| `MBDB_DATASETS_DIR` | `./examples` | built-in question sets |
| `PORT` / `MBDB_HOST` | 8000 / 127.0.0.1 (0.0.0.0 in Docker) | listen address |
| `MBDB_APP_TOKEN` | – | require `X-API-Token` or `Authorization: Bearer` |
| `MBDB_ALLOW_USER_KEYS` | true | false = only server profiles |
| `MBDB_ALLOW_CUSTOM_ENDPOINTS` | true | false = no user-supplied URLs (SSRF protection) |
| `MBDB_ENABLED_PROVIDERS` | all | comma list |
| `MBDB_RATE_LIMIT_PER_MINUTE` | 0 (off) | POST/DELETE per client IP |
| `MBDB_MAX_CONCURRENT_RUNS` / `MBDB_MAX_CASES_PER_RUN` / `MBDB_MAX_WORKERS` | 2 / 1000 / 8 | limits |
| `MBDB_RETENTION_DAYS` / `MBDB_MAX_RUNS_KEPT` | 0 / 0 (keep) | automatic cleanup of finished runs |
| `MBDB_MAX_UPLOAD_BYTES` | 2 MB | upload limit |
| `MBDB_LOG_LEVEL` | INFO | logging |
| `MBDB_DEMO_DELAY_SECONDS` | 0.15 | pacing of the demo provider |

Server profiles: `AZURE_OPENAI_*`, `AZURE_AI_FOUNDRY_*`, `GITHUB_TOKEN` + `GITHUB_MODELS`, `OLLAMA_*`, `MBDB_JUDGE_URL` + `MBDB_JUDGE_KEY` (see `.env.example`).

## API

OpenAPI docs at `/api/docs`. Endpoints: `GET /api/health`, `GET /api/ready`, `GET /api/meta`, `GET/POST /api/datasets`, `DELETE /api/datasets/{id}`, `GET/POST /api/runs`, `GET /api/runs/{id}`, `GET /api/runs/{id}/live`, `GET /api/runs/{id}/results`, `GET /api/runs/{id}/artifacts/{report.html|summary.json|results.jsonl|report.md|run_events.jsonl}`, `POST /api/runs/{id}/cancel`, `DELETE /api/runs/{id}`.

Security and production notes: docs/PRODUCTION.md.
