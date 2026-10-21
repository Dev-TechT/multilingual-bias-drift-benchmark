# Web app

The web app lets anyone test a model in the browser: pick a provider, enter a model (and their own key, or use a model pre-configured on the server), choose question sets and watch the results appear live. It is a thin layer over the same runner as the CLI, so results are identical.

## Run it

| Way | Command | URL |
| --- | --- | --- |
| Windows | `powershell -ExecutionPolicy Bypass -File .\start.ps1` | opens automatically |
| Docker Compose | `docker compose up --build` | http://localhost:8000 |
| Source | `pip install -e ".[web]"` then `fillblank-web --open` | http://127.0.0.1:8000 |

First test without any key: provider **Mock drift demo** → **Start test**. The demo answers are synthetic (marked "DEMO" in the UI) and only show how the live view works.

## Live view

![Live view during a run](img/webapp-live.png)

| Element | Meaning |
| --- | --- |
| Traffic light + sentence | "X of Y questions get different answers depending on the language". Green = consistent, yellow = up to 20 % of questions drift, red = more. Pulses while the run is active. |
| Progress bar | answers received / planned |
| Bars per language | mix of answer types for all questions in that language; the number is the share of neutral/correct answers |
| Question × language grid | one row per question, one column per language; cells fill in as answers arrive. ✓ neutral/correct · ↔ pushes back on stereotype · ! stereotype/assumption · – refused. A row with mixed colours is drift. Hover a cell for details. |

After the run: numbers, per-language table, all answers with filters (language, stance, question, judge ≠ heuristic) and downloads (`report.html`, `summary.json`, `results.jsonl`).

## Configuration (environment variables)

| Variable | Default | Purpose |
| --- | --- | --- |
| `MBDB_DATA_DIR` | `~/.multilingual-bias-drift-benchmark/web` (`/data` in Docker) | run artifacts, uploads, run history |
| `MBDB_DATASETS_DIR` | `./examples` | built-in question sets |
| `MBDB_APP_TOKEN` | – | if set, `/api/*` (except health) needs `X-API-Token` or `Authorization: Bearer` |
| `MBDB_ALLOW_USER_KEYS` | `true` | `false` = only server profiles |
| `MBDB_ALLOW_CUSTOM_ENDPOINTS` | `true` | `false` = users cannot enter base URLs (blocks SSRF) |
| `MBDB_ENABLED_PROVIDERS` | all | e.g. `mock-drift,azure-openai,github-models` |
| `MBDB_MAX_CONCURRENT_RUNS` / `MBDB_MAX_CASES_PER_RUN` / `MBDB_MAX_WORKERS` | 2 / 1000 / 8 | limits |
| `MBDB_MAX_UPLOAD_BYTES` | 2 MB | dataset upload limit |
| `MBDB_DEMO_DELAY_SECONDS` | 0.15 (web), 0 (CLI) | pacing of the demo provider |

**Server profiles** (keys stay on the server): `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_DEPLOYMENTS`, `AZURE_AI_FOUNDRY_*`, `GITHUB_TOKEN` + `GITHUB_MODELS`, `OLLAMA_BASE_URL` + `OLLAMA_MODELS`. See `.env.example`.

## Security model

- User-entered API keys live only in memory for the duration of the run — never on disk, in metadata, logs or API responses (tested).
- Strict Content-Security-Policy, no inline scripts, all model output rendered as text; reports served with their own CSP.
- Plain `http://` endpoints only for local/private hosts (and Ollama). Run/artifact/dataset ids validated; artifacts from an allow-list.

## From local test to public website

"Everyone can test it" works best as **bring-your-own-key** plus the free demo: visitors pay for their own model calls, you pay nothing per run. Before going public:

1. **Hosting:** Azure Container Apps with this Dockerfile; Azure Files volume for `/data`.
2. **Abuse protection:** rate limiting at the proxy/Front Door, `MBDB_MAX_CASES_PER_RUN`, `MBDB_MAX_CONCURRENT_RUNS`.
3. **SSRF:** with user keys allowed, keep `MBDB_ALLOW_CUSTOM_ENDPOINTS=false` unless needed, or restrict egress at network level.
4. **Optional login:** Entra ID Easy Auth if only colleagues/partners should use it; `MBDB_APP_TOKEN` for simple protection.
5. **Scale-out:** run state is in-process (one replica). Multiple replicas need a shared queue/DB — not included.
6. **Data & legal:** retention policy for stored model outputs, privacy notice/imprint, keep the caveat visible, no leaderboard without RELEASE_POLICY.md methodology, finished native-speaker review of the questions.

## API

OpenAPI docs at `/api/docs`. Main endpoints: `GET /api/meta`, `GET/POST /api/datasets`, `POST /api/runs`, `GET /api/runs/{id}`, `GET /api/runs/{id}/live`, `GET /api/runs/{id}/results`, `GET /api/runs/{id}/artifacts/{report.html|summary.json|results.jsonl|report.md}`, `POST /api/runs/{id}/cancel`, `DELETE /api/runs/{id}`.
