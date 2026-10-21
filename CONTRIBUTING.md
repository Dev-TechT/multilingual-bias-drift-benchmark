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

## Contribution and task templates

Use the focused GitHub templates so issues stay small and public-safe:

- Public case proposals: .github/ISSUE_TEMPLATE/case-proposal.yml
- Agent-friendly adapter/reporting/tooling tasks: .github/ISSUE_TEMPLATE/agent-task.yml
- Validator/adapter bug reports: .github/ISSUE_TEMPLATE/bug.yml
- Pull request checklist: .github/pull_request_template.md

For coding-agent tasks, include a narrow goal, explicit scope/non-goals, acceptance criteria, verification commands, and the privacy/claim boundary. Do not post private/client data or unsupported model claims in issue bodies, PR bodies, logs, screenshots, or artifacts.
