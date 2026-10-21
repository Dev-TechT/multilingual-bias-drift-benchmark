# Changelog

## 0.4.0

### Added
- **Your own AI as model under test:** `http-json` provider with the `mbdb.generate.v1` JSON contract (CLI + web app) and `python:<module>:<Class>` plugins (CLI only). Reference server, plugin example and JSON Schemas in `examples/custom/`. Docs: docs/CUSTOM_AI.md.
- **External judges:** `http-judge` with the `mbdb.judge.v1` contract (answer stance, score, optional confidence and per-stance probabilities). Reference judge server; mapping for decision models such as Jev. Docs: docs/JUDGES.md.
- **Confidence-based human review:** `--judge-min-confidence` / web setting; low-confidence verdicts and judge failures get `labels.needs_human_review`, counted in `summary.judge.needs_human_review`, marked "?" in the live grid, filterable in the answer table.
- **Docker distribution:** multi-arch image on GitHub Container Registry (`docker-publish.yml`, SBOM, provenance attestation, Trivy scan); `docker compose up` pulls the published image; Hugging Face Space bundle (`scripts/build_hf_space.sh`) and optional auto-deploy (`hf-space-sync.yml`); Dependabot.
- **Production features in the web app:** per-IP rate limiting (`MBDB_RATE_LIMIT_PER_MINUTE`), automatic cleanup (`MBDB_RETENTION_DAYS`, `MBDB_MAX_RUNS_KEPT`), readiness endpoint `/api/ready`, structured logs, `PORT` support, server profile for an external judge (`MBDB_JUDGE_URL`), provider roles (target/judge) enforced in API and UI.
- `scripts/start-wsl.sh`; docs: DEPLOY.md, PRODUCTION.md, CUSTOM_AI.md, JUDGES.md; rewritten README, RESULTS.md, DATA_CARD.md, CONTRIBUTING.md, BENCHMARK_SPEC.md, ROADMAP.md, SECURITY.md, WINDOWS_SETUP.md.

### Changed
- `start.ps1`: prefers WSL, never downloads Python via uv (`UV_PYTHON_PREFERENCE=only-system`), uses `UV_SYSTEM_CERTS` instead of the deprecated `UV_NATIVE_TLS`.
- Docs now state scorer coverage precisely: heuristic stereotype cues only in en/de/es/fr/pt/ru; use a judge for other languages.
- Judge version `judge-v2` (shared validation for LLM and external judges). Container user uid 1000.
- Reasoning-model fallback now actually rebuilds the request body on retry.
- pytest ignores the Starlette `httpx` deprecation warning.

### Compatibility
All CLI flags, API endpoints and artifact fields of 0.3 remain valid; new fields are additive.

## 0.3.0

- **Core-24 question set:** `examples/public_core24_15lang.jsonl`, 24 questions × 15 languages (360 rows); 27 same-question groups in 15 languages in total.
- **Live view** in the web app (traffic light, per-language bars, question × language grid), `GET /api/runs/{id}/live`, demo marker.
- Windows start script, `fillblank-web --open`, `MBDB_DEMO_DELAY_SECONDS`.

## 0.2.0 (released together with 0.3.0)

- Providers Azure OpenAI, Azure AI Foundry, GitHub Models, Ollama, `mock-drift`; retries/backoff; content-filter handling; LLM judge; parallel workers; cancellation; drift alerts, heatmap and run metadata; heuristic scorer v2; `public_top15_sample.jsonl`; web app; Dockerfile; CI matrix.
