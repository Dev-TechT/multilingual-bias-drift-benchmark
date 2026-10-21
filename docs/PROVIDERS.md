# Provider setup

`fillblank-run` and the web app run the benchmark against one model per run. All HTTP providers share retries with backoff for 408/409/429/5xx and connection errors (honouring `Retry-After`, max 30 s), error messages that never echo response bodies, and content-filter handling.

| `--provider` | Use for | Auth | Endpoint (`--base-url`) | `--model` |
| --- | --- | --- | --- | --- |
| `mock` | pipeline smoke test | none | – | `mock-model` |
| `mock-drift` | demo of the live view / reports (synthetic!) | none | – | any |
| `azure-openai` | Azure OpenAI deployments | `api-key` header | `https://<resource>.openai.azure.com` (or `.../openai/v1`) | **deployment name** |
| `azure-foundry` | Azure AI Foundry model inference (Llama, Mistral, DeepSeek, Phi, …) | `api-key` header | `https://<resource>.services.ai.azure.com/models` | model name |
| `github-models` | GitHub Models | GitHub PAT (`models:read`) | default `https://models.github.ai/inference` | e.g. `openai/gpt-4.1-mini` |
| `openai-compatible` | OpenAI, vLLM, LiteLLM, LM Studio, … | Bearer | e.g. `https://api.openai.com/v1` | model name |
| `ollama` | local models | none | default `http://localhost:11434/v1` | e.g. `llama3.1:8b` |

Aliases: `openai`, `azure`, `foundry`, `github`. `fillblank-run --list-providers` prints the table as JSON.

## Credentials via environment variables

Generic variables (`FILLBLANK_BASE_URL`, `FILLBLANK_API_KEY`, `FILLBLANK_MODEL`, `FILLBLANK_API_VERSION`) win; otherwise each provider reads its usual variables:

| Provider | Endpoint | Key | Model | API version |
| --- | --- | --- | --- | --- |
| azure-openai | `AZURE_OPENAI_ENDPOINT` | `AZURE_OPENAI_API_KEY` | `AZURE_OPENAI_DEPLOYMENT` | `AZURE_OPENAI_API_VERSION` (default `2024-10-21`) |
| azure-foundry | `AZURE_AI_FOUNDRY_ENDPOINT` / `AZURE_INFERENCE_ENDPOINT` | `AZURE_AI_FOUNDRY_API_KEY` / `AZURE_INFERENCE_CREDENTIAL` | `AZURE_AI_FOUNDRY_MODEL` | default `2024-05-01-preview` |
| github-models | – | `GITHUB_TOKEN` | `GITHUB_MODELS_MODEL` | – |
| openai-compatible | `OPENAI_BASE_URL` | `OPENAI_API_KEY` | `OPENAI_MODEL` | – |
| ollama | `OLLAMA_BASE_URL` | – | `OLLAMA_MODEL` | – |

PowerShell:

```powershell
$env:UV_NATIVE_TLS = "true"   # company proxy
$env:AZURE_OPENAI_ENDPOINT = "https://<resource>.openai.azure.com"
$env:AZURE_OPENAI_API_KEY  = "<key>"
uv run fillblank-run --provider azure-openai --model gpt-4o-mini --dataset examples/public_core24_15lang.jsonl --workers 4 --progress
```

## Options

| Option | Default | Notes |
| --- | --- | --- |
| `--workers N` | 1 | parallel requests (1–16). Start with 2–4; rate limits apply. |
| `--max-retries N` | 3 | retries for 429/5xx/timeouts |
| `--temperature` / `--max-tokens` | 0 / 256 | reasoning models switch to `max_completion_tokens` automatically |
| `--scorer judge` | heuristic | LLM judge, see below |
| `--run-label TEXT` | – | stored in `run_metadata` |
| `--out-dir` | mock: `runs/fillblank-public`; real: `~/.multilingual-bias-drift-benchmark/runs/<stamp>-<provider>-<model>` | artifacts |

## LLM judge (`--scorer judge`)

The heuristic scorer only matches phrases and misses most stereotypes outside English. With `--scorer judge` a second model classifies every answer into the four stances and the 0–3 rubric in any language. The heuristic result is kept (`heuristic_answer_stance`, `heuristic_score`); disagreements get `labels.judge_disagrees_with_heuristic = true` — review those first.

Options: `--judge-provider`, `--judge-model`, `--judge-base-url`, `--judge-api-key`, `--judge-api-version` (env `FILLBLANK_JUDGE_*` or the judge provider's usual variables). Use a strong judge from a different model family, temperature 0, and calibrate on human-labelled rows. A single judge is not an official scorer (BENCHMARK_SPEC.md).

## Content filters

Blocked prompts/completions are recorded as **completed** with `answer_stance = refusal_void`, `labels.content_filtered = true`, and counted in `summary.content_filtered`. A filter that triggers in one language but not another is itself a drift signal.

## Output guard and secrets

The fail-closed public-repo output guard from v0.1 is unchanged. API keys never appear in `results.jsonl`, `summary.json`, reports or progress events (tested). `--include-raw-response` is for local debugging only.
