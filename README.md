# Multilingual Bias Drift Benchmark

A small open-source benchmark for checking whether the same model changes its answer stance when the same underlying question is asked in different language versions.

**Core idea:** Same question. Same model. Different language. Compare whether the answer becomes anti/stereotype, pro/counter-stereotype, neutral/uncertain, or refusal/void depending on the language.

Example signal:

- English answer: anti-women / stereotype-like.
- Spanish answer: pro-women / counter-stereotype-like.
- German answer: neutral / says there is not enough information.

That language-driven answer drift is the benchmark target.

> **Important caveat:** this is a QA/regression benchmark, not proof that a model is biased, unbiased, safe, or better than another model. Public sample/dev data is for development and demonstration. Strong public claims need a reviewed methodology, private holdout design, native/competent language review, and explicit publication approval.

## Quick start

### Windows (no Docker needed)

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Opens http://127.0.0.1:8000. Choose **Mock drift demo** → **Start test** to see the live view without any key. Works behind corporate TLS inspection (uses the Windows certificate store). Details and troubleshooting: [docs/WINDOWS_SETUP.md](docs/WINDOWS_SETUP.md).

### Docker

```bash
docker compose up --build        # http://localhost:8000
```

### CLI

```bash
uv run --extra dev python -m pytest -q
uv run python -m fillblank_eval.validator examples/*.jsonl
uv run python -m fillblank_eval.duplicates examples/*.jsonl
uv run python -m fillblank_eval.leak_scan .
uv run fillblank-run --provider mock-drift --dataset examples/public_core24_15lang.jsonl --workers 4
```

Test a real model (example: Azure OpenAI, 24 questions × 15 languages, LLM judge):

```bash
export AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
export AZURE_OPENAI_API_KEY=...            # never pass keys on the command line
uv run fillblank-run --provider azure-openai --model gpt-4o-mini \
  --dataset examples/public_core24_15lang.jsonl --workers 4 \
  --scorer judge --judge-provider azure-openai --judge-model gpt-4.1
```

All providers: [docs/PROVIDERS.md](docs/PROVIDERS.md) · Web app: [docs/WEBAPP.md](docs/WEBAPP.md) · Questions: [docs/QUESTIONS.md](docs/QUESTIONS.md) · Results: [docs/RESULTS.md](docs/RESULTS.md).

## Web app with live view

The browser UI shows results **while the run is going**:

- a traffic light and one plain sentence (“7 of 24 questions get different answers depending on the language”),
- a bar per language showing the mix of answer types,
- a grid with every question (rows) in every language (columns) that fills in live — a row with different colours is a question whose answer changes with the language.

Anyone can test their own model with their own key; keys are used for the run only and never stored. Server operators can also pre-configure Azure/GitHub/Ollama models.

## What's included

- JSONL case schema, validator, duplicate/near-duplicate checks, private-data leak scan;
- runner for mock, Azure OpenAI, Azure AI Foundry, GitHub Models, OpenAI-compatible and Ollama endpoints (retries, parallel requests, content-filter handling);
- heuristic scorer (15+ languages) and an optional LLM-as-judge scorer with disagreement flags;
- reports (`summary.json`, `results.jsonl`, Markdown, HTML with drift heatmap) and run metadata for reproducibility;
- **522 public cases**, including the new core set of **24 questions × 15 languages** (`examples/public_core24_15lang.jsonl`) — 27 same-question groups in 15 languages in total;
- web app, Docker image, Windows start script;
- data-tier policy for keeping private holdouts private; Inspect AI adapter starter.

## Data tiers

Public repo tiers: `public_sample` (tiny examples for docs and smoke tests) and `public_dev` (public development examples).

| File | Rows | Languages | Notes |
| --- | ---: | --- | --- |
| `examples/public_sample.jsonl` | 12 | en, de, el | core samples |
| `examples/public_dev.jsonl` | 105 | en, de, el | paraphrase dev set |
| `examples/public_top10_sample.jsonl` | 10 | top-10 | `top10-app-001` |
| `examples/public_top15_sample.jsonl` | 35 | 15 | extends `top10-app-001`, adds 2 groups |
| `examples/public_core24_15lang.jsonl` | 360 | 15 | **24 questions × 15 languages** (v0.3) |

All multilingual rows beyond en/de/el are **translation-assisted and unreviewed**; see [docs/LANGUAGES.md](docs/LANGUAGES.md) before drawing language-specific conclusions.

Private/off-repo tiers (`private_holdout`, `quarantine_candidates`, `retired_holdout`) must never be committed, published, stored in CI artifacts, baked into Docker images, or exposed in per-sample public logs.

## What this is not

- Not a comprehensive scientific bias benchmark by itself.
- Not an alignment benchmark.
- Not a model leaderboard dataset.
- Not proof that a model is biased, unbiased, safe, compliant, fair, or production-ready.

## Key terms

- `translation_group`: one underlying question represented in multiple languages. Compare within this group.
- **answer stance**: anti/stereotype, pro/counter-stereotype, neutral/uncertain, or refusal/void.
- **drift**: a change in answer stance across language versions of the same question for the same model/run settings.

## Relationship to existing benchmarks

Inspired by and to be compared carefully against BBQ, Open-BBQ, StereoSet, HONEST, UnknownBench, SelfAware, TruthfulQA, XSTest, and DecodingTrust. The niche here is practical detection of multilingual answer drift for equivalent prompts.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT.
