# Roadmap

## Now (before public launch)
- Native-speaker review of all translated rows (review sheet).
- Verify Azure OpenAI, Azure AI Foundry, GitHub Models and Ollama against real endpoints.
- Calibrate judges on hand-labelled answers; document recommended confidence thresholds.
- Hugging Face demo Space; Azure Container Apps for internal use with Entra ID.

## Next
- More questions: ≥ 20–30 per construct and language; contrast controls.
- Private holdout workflow for official numbers.
- Run comparison view (model A vs. B, before/after a prompt change).
- Queue-based workers for multi-replica deployments.
- Optional per-user accounts and quotas.

## Later
- Agent/trajectory evaluation (multi-turn answers).
- More languages beyond the 15-language set where reviewers are available.
- Export to evaluation platforms (Inspect AI, promptfoo, lm-evaluation-harness).
