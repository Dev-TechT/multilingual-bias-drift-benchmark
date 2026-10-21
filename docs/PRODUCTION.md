# Production readiness

Status of v0.4.0 and what is still needed before a public, unattended service.

## Built in

| Area | What exists |
| --- | --- |
| Secrets | user keys only in memory for the run; never in files, metadata, logs or API responses (tested); server keys via env/secrets; error bodies of providers never shown |
| Web security | strict CSP, no inline scripts, `nosniff`, no-referrer, frame protection, all model output rendered as text, artifact allow-list, validated ids |
| Abuse limits | `MBDB_RATE_LIMIT_PER_MINUTE` (per client IP), max cases/run, max parallel runs, max workers, upload size, optional `MBDB_APP_TOKEN` |
| SSRF | `MBDB_ALLOW_CUSTOM_ENDPOINTS=false` blocks user-supplied URLs; plain http only for private hosts; Python providers never loadable from the web |
| Data lifecycle | `MBDB_RETENTION_DAYS`, `MBDB_MAX_RUNS_KEPT`; uploads validated (public tiers only) |
| Operations | `/api/health` (liveness), `/api/ready` (readiness), structured access logs for state-changing calls, container health check, non-root image |
| Reliability | retries with backoff, per-case isolation, cancellation, restart-safe run history |
| Reproducibility | `run_metadata` (versions, settings, prompt wrapper, dataset SHA-256), heuristic kept next to judge verdicts |
| Supply chain | CI on Python 3.10/3.12, Docker smoke test, multi-arch image with SBOM + provenance, Trivy scan, Dependabot |

## Still to do before a public launch

| # | Item | Why | Suggested solution |
| ---: | --- | --- | --- |
| 1 | Native-speaker review of all translated rows | language-specific results are otherwise noise | review sheet (Excel), fix rows, set `review_status` |
| 2 | Judge calibration | judge accuracy unknown | 50–100 hand-labelled answers across languages; pick confidence threshold (docs/JUDGES.md) |
| 3 | Authentication for non-demo use | cost and abuse control | Entra ID (Azure) or OAuth proxy; per-user quotas |
| 4 | Edge rate limiting / WAF | in-app limiter is per container and per IP only | Azure Front Door / Cloudflare rules |
| 5 | Scale-out | run state is in-process (single replica) | queue (Azure Storage Queue / Redis) + worker, DB for run metadata |
| 6 | Persistent storage + backup | results lost on container replacement | Azure Files / volume, retention policy |
| 7 | Legal | public website obligations | imprint, privacy notice (prompts/answers are stored), terms of use, caveat on every page |
| 8 | Monitoring | detect failures and abuse | log shipping (Azure Monitor), alerts on 5xx / 429 / run failures |
| 9 | More questions | 1 row per language per question is not statistics | ≥ 20–30 questions per construct and language; private holdout for official numbers |
| 10 | Real-endpoint verification | Azure/Foundry/GitHub endpoints are only tested against fakes | one run per provider with real credentials; record in QA_REPORT |

## Release process

1. Branch `release/vX.Y.Z`, update `CHANGELOG.md` and the version in `pyproject.toml` / `src/fillblank_eval/__init__.py`.
2. Pull request → CI green → merge.
3. Tag `vX.Y.Z` on `main` (GitHub Release) → image `ghcr.io/…:X.Y.Z` and `:latest`, optional Hugging Face deploy.
4. Smoke test the published image (`docker run …` → demo run).
