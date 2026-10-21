# Contributing

Thanks for helping improve the Multilingual Bias Drift Benchmark.

## Good contributions

- native/competent review of translated rows (most valuable right now);
- new same-question groups across the 15 languages;
- provider adapters, judge relays, report/UI improvements, docs;
- validator/scorer bug fixes and duplicate-detection improvements.

## Benchmark item checklist

For any new case: one primary construct; exactly one `{blank}`; expected behaviour; rubric; language and review status; `translation_group` for multilingual groups; protected classes (may be empty); provenance/licence; duplicate check; contamination note; `review.public_release_ok=true` only when safe.

## Do not contribute

Slur-bait or shock-bait prompts; race/gender/nationality ranking prompts; private, client, personal or scraped data; private holdout rows, raw provider logs, credentials; claims that the benchmark proves a model safe/aligned/unbiased/fair; leaderboard or production-readiness claims.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[web,dev]"
.venv/bin/python -m pytest -q
.venv/bin/python -m fillblank_eval.validator examples/*.jsonl
.venv/bin/python -m fillblank_eval.duplicates examples/*.jsonl
.venv/bin/python -m fillblank_eval.leak_scan .
.venv/bin/fillblank-web --open
```

Branch → pull request → CI green → merge. Data-changing PRs need a methodology/safety review and a language/quality review.

## Templates

Issue templates in `.github/ISSUE_TEMPLATE/` (case proposal, agent task, bug) and `.github/pull_request_template.md`. For coding-agent tasks include goal, scope/non-goals, acceptance criteria, verification commands and the privacy/claim boundary.
