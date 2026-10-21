"""Runtime settings for the web app, read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from fillblank_eval.provider_client import PROVIDERS


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None or not value.strip() else value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _list(name: str) -> list[str]:
    return [item.strip() for item in (os.environ.get(name) or "").split(",") if item.strip()]


def _default_datasets_dir() -> Path:
    candidates = [Path(os.environ["MBDB_DATASETS_DIR"]) if os.environ.get("MBDB_DATASETS_DIR") else None,
                  Path(__file__).resolve().parents[2] / "examples", Path.cwd() / "examples", Path("/app/examples")]
    return next((c for c in candidates if c is not None and c.is_dir()), Path.cwd() / "examples")


@dataclass(frozen=True)
class ServerProfile:
    """A provider configured by the operator via environment variables (keys stay server-side)."""

    name: str
    provider: str
    label: str
    models: list[str]
    base_url: str | None = None
    api_key: str | None = field(default=None, repr=False)
    api_version: str | None = None

    def public_view(self) -> dict:
        return {"name": self.name, "provider": self.provider, "label": self.label, "models": self.models, "has_key": bool(self.api_key),
                "role": PROVIDERS.get(self.provider, {}).get("role", "both")}


def _server_profiles() -> dict[str, ServerProfile]:
    env = os.environ
    profiles: dict[str, ServerProfile] = {}
    if env.get("AZURE_OPENAI_ENDPOINT") and env.get("AZURE_OPENAI_API_KEY"):
        profiles["azure-openai"] = ServerProfile("azure-openai", "azure-openai", "Azure OpenAI (server)", _list("AZURE_OPENAI_DEPLOYMENTS") or _list("AZURE_OPENAI_DEPLOYMENT"),
                                                 env["AZURE_OPENAI_ENDPOINT"], env["AZURE_OPENAI_API_KEY"], env.get("AZURE_OPENAI_API_VERSION") or None)
    if env.get("AZURE_AI_FOUNDRY_ENDPOINT") and env.get("AZURE_AI_FOUNDRY_API_KEY"):
        profiles["azure-foundry"] = ServerProfile("azure-foundry", "azure-foundry", "Azure AI Foundry (server)", _list("AZURE_AI_FOUNDRY_MODELS"),
                                                  env["AZURE_AI_FOUNDRY_ENDPOINT"], env["AZURE_AI_FOUNDRY_API_KEY"], env.get("AZURE_AI_FOUNDRY_API_VERSION") or None)
    if env.get("GITHUB_TOKEN"):
        profiles["github-models"] = ServerProfile("github-models", "github-models", "GitHub Models (server)",
                                                  _list("GITHUB_MODELS") or ["openai/gpt-4.1-mini", "openai/gpt-4o-mini", "meta/Llama-3.3-70B-Instruct"], None, env["GITHUB_TOKEN"])
    if env.get("OLLAMA_BASE_URL"):
        profiles["ollama"] = ServerProfile("ollama", "ollama", "Ollama (server)", _list("OLLAMA_MODELS"), env["OLLAMA_BASE_URL"])
    if env.get("MBDB_JUDGE_URL"):
        profiles["http-judge"] = ServerProfile("http-judge", "http-judge", env.get("MBDB_JUDGE_LABEL") or "External judge (server)", ["default"],
                                               env["MBDB_JUDGE_URL"], env.get("MBDB_JUDGE_KEY") or None)
    return profiles


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    datasets_dir: Path
    app_token: str | None
    max_concurrent_runs: int
    max_cases_per_run: int
    max_workers: int
    allow_user_keys: bool
    allow_custom_endpoints: bool
    enabled_providers: list[str]
    max_upload_bytes: int
    profiles: dict[str, ServerProfile]
    retention_days: int = 0
    rate_limit_per_minute: int = 0
    max_runs_kept: int = 0

    @classmethod
    def from_env(cls) -> "Settings":
        enabled = _list("MBDB_ENABLED_PROVIDERS") or list(PROVIDERS)
        return cls(
            data_dir=Path(os.environ.get("MBDB_DATA_DIR") or "~/.multilingual-bias-drift-benchmark/web").expanduser(),
            datasets_dir=_default_datasets_dir(),
            app_token=os.environ.get("MBDB_APP_TOKEN") or None,
            max_concurrent_runs=max(1, _int("MBDB_MAX_CONCURRENT_RUNS", 2)),
            max_cases_per_run=max(1, _int("MBDB_MAX_CASES_PER_RUN", 1000)),
            max_workers=max(1, min(16, _int("MBDB_MAX_WORKERS", 8))),
            allow_user_keys=_bool("MBDB_ALLOW_USER_KEYS", True),
            allow_custom_endpoints=_bool("MBDB_ALLOW_CUSTOM_ENDPOINTS", True),
            enabled_providers=[name for name in enabled if name in PROVIDERS],
            max_upload_bytes=max(1024, _int("MBDB_MAX_UPLOAD_BYTES", 2 * 1024 * 1024)),
            profiles=_server_profiles(),
            retention_days=max(0, _int("MBDB_RETENTION_DAYS", 0)),
            rate_limit_per_minute=max(0, _int("MBDB_RATE_LIMIT_PER_MINUTE", 0)),
            max_runs_kept=max(0, _int("MBDB_MAX_RUNS_KEPT", 0)),
        )
