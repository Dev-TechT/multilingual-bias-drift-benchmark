"""Plug YOUR OWN AI in as a Python class (CLI only; the web app does not load arbitrary code).

Use:  PYTHONPATH=examples/custom fillblank-run --provider python:my_provider:MyModel --dataset examples/public_core24_15lang.jsonl
"""
from __future__ import annotations

from fillblank_eval.provider_client import CompletionResult, ProviderClient, ProviderConfig


class MyModel(ProviderClient):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config  # model name, api_key, base_url, temperature, max_tokens ... from the CLI/env

    def complete(self, prompt: str, *, case_id: str) -> CompletionResult:
        text = "The scenario does not provide enough information to determine that."  # call your model here
        return CompletionResult(provider="my-model", model=self.config.model, case_id=case_id, text=text)
