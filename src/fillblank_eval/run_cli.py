from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

from .provider_client import PROVIDERS, ProviderError, normalize_provider
from .runner import MAX_WORKERS, MOCK_PROVIDERS, SCORER_MODES, RunnerConfig, run_benchmark

DEFAULT_PUBLIC_DATASETS = [
    Path("examples/public_sample.jsonl"),
    Path("examples/public_dev.jsonl"),
    Path("examples/public_top10_sample.jsonl"),
    Path("examples/public_top15_sample.jsonl"),
    Path("examples/public_core24_15lang.jsonl"),
]
DEFAULT_MOCK_OUT_DIR = Path("runs/fillblank-public")
DEFAULT_PRIVATE_RUNS_ROOT = Path("~/.multilingual-bias-drift-benchmark/runs")

_PROVIDER_ENV = {
    "azure-openai": {"base_url": ["AZURE_OPENAI_ENDPOINT"], "api_key": ["AZURE_OPENAI_API_KEY"], "model": ["AZURE_OPENAI_DEPLOYMENT"], "api_version": ["AZURE_OPENAI_API_VERSION"]},
    "azure-foundry": {"base_url": ["AZURE_AI_FOUNDRY_ENDPOINT", "AZURE_INFERENCE_ENDPOINT"], "api_key": ["AZURE_AI_FOUNDRY_API_KEY", "AZURE_INFERENCE_CREDENTIAL"], "model": ["AZURE_AI_FOUNDRY_MODEL"], "api_version": []},
    "github-models": {"base_url": [], "api_key": ["GITHUB_TOKEN"], "model": ["GITHUB_MODELS_MODEL"], "api_version": []},
    "openai-compatible": {"base_url": ["OPENAI_BASE_URL"], "api_key": ["OPENAI_API_KEY"], "model": ["OPENAI_MODEL"], "api_version": []},
    "ollama": {"base_url": ["OLLAMA_BASE_URL"], "api_key": [], "model": ["OLLAMA_MODEL"], "api_version": []},
    "http-json": {"base_url": ["MBDB_CUSTOM_AI_URL"], "api_key": ["MBDB_CUSTOM_AI_KEY"], "model": [], "api_version": []},
    "http-judge": {"base_url": ["MBDB_JUDGE_URL"], "api_key": ["MBDB_JUDGE_KEY"], "model": [], "api_version": []},
}


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in {None, ""} else default


def _first_env(names: list[str]) -> str | None:
    return next((value for value in (_env(n) for n in names) if value), None)


def _resolve(explicit: str | None, generic_env: str, provider: str, key: str) -> str | None:
    return explicit or _env(generic_env) or _first_env(_PROVIDER_ENV.get(provider, {}).get(key, []))


def _default_out_dir(provider: str, model: str) -> Path:
    if provider in MOCK_PROVIDERS:
        return DEFAULT_MOCK_OUT_DIR
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{provider}-{model}").strip("-")[:80]
    return (DEFAULT_PRIVATE_RUNS_ROOT / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{slug}").expanduser()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run multilingual bias drift benchmark cases against a provider/model.",
                                     epilog="Providers: " + ", ".join(PROVIDERS) + ", python:<module>:<Class>. Use --list-providers for details.")
    parser.add_argument("--dataset", action="append", type=Path, help="Public JSONL dataset path; can be repeated")
    parser.add_argument("--out-dir", type=Path, default=None, help="Artifact directory (default: runs/fillblank-public for mock, ~/.multilingual-bias-drift-benchmark/runs/<stamp> otherwise)")
    parser.add_argument("--provider", default=_env("FILLBLANK_PROVIDER", "mock"), help="mock, mock-drift, azure-openai, azure-foundry, github-models, openai-compatible, ollama, http-json, python:<module>:<Class>")
    parser.add_argument("--base-url", default=None, help="Provider endpoint (env: FILLBLANK_BASE_URL or provider-specific)")
    parser.add_argument("--api-key", default=None, help="API key; prefer environment variables")
    parser.add_argument("--api-version", default=None, help="Azure api-version")
    parser.add_argument("--model", default=None, help="Model or Azure deployment name")
    parser.add_argument("--temperature", type=float, default=float(_env("FILLBLANK_TEMPERATURE", "0") or 0))
    parser.add_argument("--max-tokens", type=int, default=int(_env("FILLBLANK_MAX_TOKENS", "256") or 256))
    parser.add_argument("--timeout-seconds", type=int, default=int(_env("FILLBLANK_TIMEOUT_SECONDS", "60") or 60))
    parser.add_argument("--max-retries", type=int, default=int(_env("FILLBLANK_MAX_RETRIES", "3") or 3))
    parser.add_argument("--workers", type=int, default=int(_env("FILLBLANK_WORKERS", "1") or 1), help=f"Parallel requests (1-{MAX_WORKERS})")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--scorer", choices=SCORER_MODES, default=_env("FILLBLANK_SCORER", "heuristic"))
    parser.add_argument("--judge-provider", default=_env("FILLBLANK_JUDGE_PROVIDER"), help="Any chat provider (LLM judge) or http-judge (external evaluator)")
    parser.add_argument("--judge-model", default=_env("FILLBLANK_JUDGE_MODEL"))
    parser.add_argument("--judge-base-url", default=_env("FILLBLANK_JUDGE_BASE_URL"))
    parser.add_argument("--judge-api-key", default=_env("FILLBLANK_JUDGE_API_KEY"))
    parser.add_argument("--judge-api-version", default=_env("FILLBLANK_JUDGE_API_VERSION"))
    parser.add_argument("--judge-min-confidence", type=float, default=float(_env("FILLBLANK_JUDGE_MIN_CONFIDENCE", "0.6") or 0.6),
                        help="Verdicts with lower confidence are flagged needs_human_review (only if the judge returns confidence)")
    parser.add_argument("--run-label", default=None)
    parser.add_argument("--include-raw-response", action="store_true")
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--progress-jsonl", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Force credential-free mock provider")
    parser.add_argument("--list-providers", action="store_true")
    parser.add_argument("--run-scope", choices=["public", "private-client"], default="public")
    args = parser.parse_args(argv)
    if args.list_providers:
        print(json.dumps(PROVIDERS, indent=2))
        return 0
    provider = "mock" if args.dry_run else normalize_provider(args.provider)
    if args.dry_run:
        model, base_url, api_key, api_version = "mock-model", None, None, None
    else:
        model = _resolve(args.model, "FILLBLANK_MODEL", provider, "model") or ("mock-model" if provider in MOCK_PROVIDERS else ("custom" if provider == "http-json" or provider.startswith("python:") else None))
        base_url = _resolve(args.base_url, "FILLBLANK_BASE_URL", provider, "base_url")
        api_key = _resolve(args.api_key, "FILLBLANK_API_KEY", provider, "api_key")
        api_version = _resolve(args.api_version, "FILLBLANK_API_VERSION", provider, "api_version")
    if not model:
        print("FAILED")
        print("- a model / deployment name is required (--model or FILLBLANK_MODEL)")
        return 1
    judge_provider = normalize_provider(args.judge_provider) if args.judge_provider else None
    judge_api_key, judge_base_url = args.judge_api_key, args.judge_base_url
    if args.scorer == "judge" and judge_provider:
        judge_api_key = judge_api_key or _first_env(_PROVIDER_ENV.get(judge_provider, {}).get("api_key", []))
        judge_base_url = judge_base_url or _first_env(_PROVIDER_ENV.get(judge_provider, {}).get("base_url", []))
    out_dir = args.out_dir or _default_out_dir(provider, model)
    config = RunnerConfig(
        dataset_paths=args.dataset or [p for p in DEFAULT_PUBLIC_DATASETS if p.exists()] or DEFAULT_PUBLIC_DATASETS,
        out_dir=out_dir, provider=provider, base_url=base_url, api_key=api_key, model=model, temperature=args.temperature,
        max_tokens=args.max_tokens, timeout_seconds=args.timeout_seconds, limit=args.limit, include_raw_response=args.include_raw_response,
        progress=args.progress, progress_jsonl=args.progress_jsonl, run_scope=args.run_scope, api_version=api_version,
        max_retries=args.max_retries, workers=args.workers, scorer=args.scorer, judge_provider=judge_provider, judge_model=args.judge_model,
        judge_base_url=judge_base_url, judge_api_key=judge_api_key, judge_api_version=args.judge_api_version,
        judge_min_confidence=args.judge_min_confidence, run_label=args.run_label,
    )
    try:
        result = run_benchmark(config)
    except ProviderError as exc:
        print(f"Provider error: {exc}")
        return 2
    if result.ok:
        for name in ("results.jsonl", "summary.json", "report.md", "report.html"):
            print(f"OK: wrote {out_dir / name}")
        print(f"Drift alerts: {len((result.summary or {}).get('drift_alerts') or [])} same-question group(s) changed stance across languages")
        return 0
    print("FAILED")
    for error in result.errors:
        print(f"- {error}")
    if result.out_dir is not None:
        print(f"Partial artifacts: {result.out_dir}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
