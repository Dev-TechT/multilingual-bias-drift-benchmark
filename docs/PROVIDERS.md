# Providers

| `--provider` | Use for | Auth | Endpoint (`--base-url`) | `--model` |
| --- | --- | --- | --- | --- |
| `mock` | pipeline smoke test | none | – | `mock-model` |
| `mock-drift` | demo of live view / reports (synthetic!) | none | – | any |
| `azure-openai` | Azure OpenAI deployments | `api-key` header | `https://<resource>.openai.azure.com` (or `.../openai/v1`) | **deployment name** |
| `azure-foundry` | Azure AI Foundry model inference | `api-key` header | `https://<resource>.services.ai.azure.com/models` | model name |
| `github-models` | GitHub Models | PAT with `models:read` | default `https://models.github.ai/inference` | e.g. `openai/gpt-4.1-mini` |
| `openai-compatible` | OpenAI, vLLM, LiteLLM, LM Studio … | Bearer | e.g. `https://api.openai.com/v1` | model name |
| `ollama` | local models | none | default `http://localhost:11434/v1` | e.g. `llama3.1:8b` |
| `http-json` | **your own AI** (`mbdb.generate.v1`) | optional Bearer | your URL | optional label |
| `python:<module>:<Class>` | **your own AI** as Python class (CLI only) | – | – | optional |
| `http-judge` | external judge (judge role only) | optional Bearer | your judge URL | – |

Aliases: `openai`, `azure`, `foundry`, `github`, `custom`. `fillblank-run --list-providers` prints the table.

**Verification status:** request formats follow the providers' documented APIs and are tested against protocol-compatible fake servers. A run against each real endpoint is still outstanding (docs/PRODUCTION.md #10).

## Credentials via environment variables

`FILLBLANK_BASE_URL`, `FILLBLANK_API_KEY`, `FILLBLANK_MODEL`, `FILLBLANK_API_VERSION` win; otherwise:

| Provider | Endpoint | Key | Model | API version |
| --- | --- | --- | --- | --- |
| azure-openai | `AZURE_OPENAI_ENDPOINT` | `AZURE_OPENAI_API_KEY` | `AZURE_OPENAI_DEPLOYMENT` | `AZURE_OPENAI_API_VERSION` (default `2024-10-21`) |
| azure-foundry | `AZURE_AI_FOUNDRY_ENDPOINT` / `AZURE_INFERENCE_ENDPOINT` | `AZURE_AI_FOUNDRY_API_KEY` / `AZURE_INFERENCE_CREDENTIAL` | `AZURE_AI_FOUNDRY_MODEL` | default `2024-05-01-preview` |
| github-models | – | `GITHUB_TOKEN` | `GITHUB_MODELS_MODEL` | – |
| openai-compatible | `OPENAI_BASE_URL` | `OPENAI_API_KEY` | `OPENAI_MODEL` | – |
| ollama | `OLLAMA_BASE_URL` | – | `OLLAMA_MODEL` | – |
| http-json | `MBDB_CUSTOM_AI_URL` | `MBDB_CUSTOM_AI_KEY` | – | – |
| http-judge | `MBDB_JUDGE_URL` | `MBDB_JUDGE_KEY` | – | – |

```bash
export AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
export AZURE_OPENAI_API_KEY=<key>
fillblank-run --provider azure-openai --model gpt-4o-mini --dataset examples/public_core24_15lang.jsonl --workers 4 --progress
```

## Options

| Option | Default | Notes |
| --- | --- | --- |
| `--workers N` | 1 | parallel requests (1–16); start with 2–4 |
| `--max-retries N` | 3 | 408/409/429/5xx/timeouts, honours `Retry-After` |
| `--temperature` / `--max-tokens` | 0 / 256 | reasoning models switch to `max_completion_tokens` automatically |
| `--scorer judge` + `--judge-*` | heuristic | docs/JUDGES.md |
| `--judge-min-confidence` | 0.6 | lower-confidence verdicts → `needs_human_review` |
| `--run-label` | – | stored in `run_metadata` |
| `--out-dir` | mock: `runs/fillblank-public`; others: `~/.multilingual-bias-drift-benchmark/runs/<stamp>-<provider>-<model>` | artifacts |

## Content filters

Blocked prompts/completions are recorded as completed `refusal_void` with `labels.content_filtered = true` and counted in `summary.content_filtered`. A filter triggering in one language only is itself a drift signal.

## Output guard and secrets

Non-mock runs may not write inside the repository (fail-closed guard). API keys never appear in artifacts or events (tested). `--include-raw-response` is for local debugging only.
