# Multilingual Bias Drift Benchmark

**Same question. Same model. Different language. Does the answer change?**

This benchmark asks a model the same fill-in-the-blank question in up to 15 languages and shows whether the answer stance drifts — e.g. a stereotype in English, a counter-stereotype in Spanish, "not enough information" in German, a refusal in Arabic. A web app shows the results live; a CLI and Docker image make it usable in pipelines.

> **Caveat:** a language-drift QA signal, not proof that a model is biased, unbiased, safe, or better than another model. Translation-assisted rows still need native review before language-specific claims (docs/LANGUAGES.md).

## Quick start

| You have | Do this | Then open |
| --- | --- | --- |
| **Docker** (or Podman) | `docker run --rm -p 127.0.0.1:8000:8000 -v mbdb-data:/data ghcr.io/dev-techt/multilingual-bias-drift-benchmark:latest` | http://localhost:8000 |
| **Linux / macOS / WSL** | `bash scripts/start-wsl.sh` | http://localhost:8000 |
| **Windows** | `powershell -ExecutionPolicy Bypass -File .\start.ps1` (uses WSL if present, see docs/WINDOWS_SETUP.md) | opens automatically |
| **Nothing installed** | use the hosted demo (Hugging Face Space, if published — see docs/DEPLOY.md) | – |

Pick **Mock drift demo** → **Start test** to see the live view without any key. Then choose a real provider and enter your own key (used for the run only, never stored).

Podman: replace `docker` with `podman`; the image is OCI-compatible.

## What you can test

| Provider | Typical use |
| --- | --- |
| Azure OpenAI, Azure AI Foundry, GitHub Models, OpenAI-compatible (OpenAI, vLLM, LiteLLM …), Ollama | hosted or local models |
| **Your own AI** — `http-json` | anything behind a tiny JSON contract (`mbdb.generate.v1`): internal APIs, agents, RAG pipelines → docs/CUSTOM_AI.md |
| **Your own AI** — `python:<module>:<Class>` | a Python class in your code base (CLI only) → docs/CUSTOM_AI.md |

## How answers are scored

| Scorer | Languages | Cost | When |
| --- | --- | --- | --- |
| Heuristic (default) | "not enough information" in ~20 languages; stereotype cues only in en/de/es/fr/pt/ru | free | smoke tests |
| LLM judge | all | model calls | normal use |
| External judge (`http-judge`, `mbdb.judge.v1`) | all | depends | decision models such as Jev, your own evaluator; supports confidence → low-confidence answers are flagged for human review |

Details: docs/JUDGES.md. The heuristic result is always stored next to the judge verdict; disagreements are flagged.

## Data

| File | Rows | Languages | Notes |
| --- | ---: | --- | --- |
| `examples/public_core24_15lang.jsonl` | 360 | 15 | **24 questions × 15 languages** (default in the web app) |
| `examples/public_top15_sample.jsonl` | 35 | 15 | extends `top10-app-001`, adds 2 groups |
| `examples/public_top10_sample.jsonl` | 10 | 10 | `top10-app-001` |
| `examples/public_dev.jsonl` | 105 | en, de, el | paraphrase dev set |
| `examples/public_sample.jsonl` | 12 | en, de, el | core samples |

27 same-question groups cover all 15 languages (docs/QUESTIONS.md). Own question sets can be uploaded in the web app (JSONL, `schema/fillblank.schema.json`).

## CLI

```bash
pip install -e ".[web,dev]"
python -m pytest -q
fillblank-run --provider mock-drift --dataset examples/public_core24_15lang.jsonl --workers 4
fillblank-run --provider azure-openai --model gpt-4o-mini --dataset examples/public_core24_15lang.jsonl \
  --workers 4 --scorer judge --judge-provider azure-openai --judge-model gpt-4.1     # keys via env, see docs/PROVIDERS.md
```

Artifacts: `results.jsonl`, `summary.json`, `report.md`, `report.html` (docs/RESULTS.md).

## Documentation

| Topic | File |
| --- | --- |
| Providers and credentials | docs/PROVIDERS.md |
| Connect your own AI | docs/CUSTOM_AI.md |
| Judges (LLM, external, Jev) | docs/JUDGES.md |
| Web app and live view | docs/WEBAPP.md |
| Docker, GHCR, Hugging Face, Azure | docs/DEPLOY.md |
| Production checklist | docs/PRODUCTION.md |
| Windows / WSL / company proxy | docs/WINDOWS_SETUP.md |
| Questions and languages | docs/QUESTIONS.md, docs/LANGUAGES.md |
| Reading results | docs/RESULTS.md |
| Methodology and claims | BENCHMARK_SPEC.md, RELEASE_POLICY.md, DATA_TIERS.md |

## What this is not

Not a comprehensive scientific bias benchmark, not an alignment benchmark, not a leaderboard, not proof of fairness, safety, compliance or production readiness of any model. Compare carefully with BBQ, Open-BBQ, StereoSet, HONEST, XSTest and similar benchmarks.

## Data tiers

Only `public_sample` and `public_dev` rows belong in this repo. Private tiers (`private_holdout`, `quarantine_candidates`, `retired_holdout`) must never be committed, published, baked into images or exposed in public logs (DATA_TIERS.md).

## Contributing · Security · License

CONTRIBUTING.md · SECURITY.md · MIT
