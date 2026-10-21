# Security policy

## Reporting

Please report vulnerabilities privately via GitHub **Security → Report a vulnerability** on this repository. Do not open public issues for security problems. Expect a first response within 7 days.

## Scope

The web app (`src/fillblank_web`), the runner/provider clients (`src/fillblank_eval`), the container image and the CI workflows.

## Design principles

- User API keys are held in memory for one run only and never persisted or returned (covered by tests).
- Provider error bodies are never shown; secret-like strings in errors are redacted.
- Strict CSP, no inline scripts, model output rendered as text.
- SSRF controls (`MBDB_ALLOW_CUSTOM_ENDPOINTS`), rate limiting, upload validation, non-root container.
- Private benchmark tiers must never enter the repo, images or CI artifacts (leak scan in CI).

Operational hardening for public deployments: docs/PRODUCTION.md.
