# Changelog

## 0.3.0

### Added
- **Core-24 question set** `examples/public_core24_15lang.jsonl`: 24 questions × 15 languages (360 rows) — 6 uncertainty, 5 role/gender, 3 nationality, 3 false-premise, 2 emotion-generalisation questions and 5 positive controls (2 of them counter-stereotypical facts). 27 same-question groups in 15 languages in total. See docs/QUESTIONS.md.
- **Live view** in the web app: traffic light + plain-language verdict, progress bar, answer mix per language, question × language grid that fills in while the run is going; `GET /api/runs/{id}/live`; "DEMO" marker for mock runs.
- Runner events now carry `translation_group` and `answer_stance` (also for failed cases).
- **Windows**: `start.ps1` (uv or installed Python, Windows certificate store for corporate TLS inspection, `-Test`, `-NoUv`, `-Port`), docs/WINDOWS_SETUP.md.
- `fillblank-web --open`; `MBDB_DEMO_DELAY_SECONDS` to pace the demo provider (0.15 s in the web app).
- `uv.lock` updated for the new extras.

### Changed
- Web UI simplified: two steps ("Test a model", "Your runs"), advanced settings collapsed, Core-24 selected by default.
- Default CLI datasets include `public_core24_15lang.jsonl`.

## 0.2.0 (first delivered together with 0.3.0)

- Providers: `azure-openai`, `azure-foundry`, `github-models`, `ollama`, `mock-drift`; retries/backoff (`Retry-After`), reasoning-model token parameter switch, structured refusals.
- Content-filter blocks recorded as `refusal_void` (`labels.content_filtered`, `summary.content_filtered`).
- Optional LLM-as-judge scorer with heuristic comparison and disagreement flags.
- Parallel workers with stable order, cancellation, event callback; readable configuration errors (`ProviderConfigError`).
- `summary.json`: `drift_alerts`, `language_stances`, `run_metadata` (versions, settings, dataset SHA-256, timings); reports with drift alerts and heatmap.
- Heuristic scorer `heuristic-v2` (15+ languages, negation-aware, empty output = void). v0.1 and v0.2+ scores are not strictly comparable; `run_metadata.scorer_version` records the version.
- `examples/public_top15_sample.jsonl`; validator accepts 26 language codes.
- Web app (FastAPI + vanilla JS), Dockerfile, docker-compose, `.env.example`, CI matrix (3.10/3.12) with Docker health check.

### Compatibility
All v0.1 public APIs, CLI flags, artifact fields and tests remain valid; new fields are additive.
