"""Provider clients for the multilingual bias drift benchmark.

Supported providers (``ProviderConfig.provider``):

- ``mock`` / ``dry-run``: credential-free, always neutral. Pipeline smoke test only.
- ``mock-drift``: credential-free demo that deliberately returns different stances per
  language so reports/UI can be demonstrated. Never use for model evidence.
- ``openai-compatible`` / ``openai``: any OpenAI-style ``/chat/completions`` endpoint. Bearer auth.
- ``azure-openai``: ``{endpoint}/openai/deployments/{deployment}/chat/completions?api-version=...``
  with ``api-key`` header (or the Azure ``/openai/v1`` endpoint). ``model`` is the deployment name.
- ``azure-foundry``: Azure AI Foundry model inference (``https://<resource>.services.ai.azure.com/models``).
- ``github-models``: GitHub Models (``https://models.github.ai/inference``), GitHub PAT with ``models:read``.
- ``ollama``: local Ollama OpenAI-compatible API (``http://localhost:11434/v1``), no key.

All HTTP providers share retry/backoff for 429/5xx/timeouts, never echo response bodies
in errors, and map content-filter blocks to :class:`ContentFilteredError`.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant. Answer the user's prompt concisely."
DEFAULT_AZURE_OPENAI_API_VERSION = "2024-10-21"
DEFAULT_AZURE_FOUNDRY_API_VERSION = "2024-05-01-preview"
DEFAULT_GITHUB_MODELS_BASE_URL = "https://models.github.ai/inference"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
MAX_RETRY_AFTER_SECONDS = 30.0

_sleep: Callable[[float], None] = time.sleep  # indirection so tests can avoid real sleeping


class ProviderError(RuntimeError):
    """Raised when a provider cannot be configured or called safely."""


class ProviderConfigError(ProviderError):
    """Local configuration problem (missing key/URL/model). Messages are constant text written by
    this package and never contain secrets, so they may be shown unredacted."""


class ContentFilteredError(ProviderError):
    """The provider's safety/content filter blocked the prompt or completion.

    For this benchmark a filter block is an *answer stance* (``refusal_void``), not an infrastructure failure.
    """


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = None
    temperature: float | None = 0.0
    max_tokens: int = 256
    timeout_seconds: int = 60
    include_raw_response: bool = False
    api_version: str | None = None
    max_retries: int = 3
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    use_max_completion_tokens: bool = False
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CompletionResult:
    provider: str
    model: str
    case_id: str
    text: str
    raw_response: dict[str, Any] | None = None
    finish_reason: str | None = None
    latency_ms: int | None = None


class ProviderClient:
    def complete(self, prompt: str, *, case_id: str) -> CompletionResult:
        raise NotImplementedError


class MockProviderClient(ProviderClient):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def complete(self, prompt: str, *, case_id: str) -> CompletionResult:
        text = "The scenario does not provide enough information to determine the blank."
        return CompletionResult(provider="mock", model=self.config.model, case_id=case_id, text=text)


_DRIFT_DEMO_OUTPUTS = (
    "The scenario does not provide enough information to determine that.",
    "We should not assume age or gender here; stereotypes are not supported by the scenario.",
    "It must have been the older person, obviously.",
    "I cannot answer any question about this topic.",
)


class MockDriftProviderClient(ProviderClient):
    """Deterministic demo client that produces cross-language stance drift (synthetic!).

    The answer depends on a hash of the case id, so runs are reproducible. Positive controls get a direct answer.
    An optional small delay makes the live view visible in demos.
    """

    def __init__(self, config: ProviderConfig, delay_seconds: float = 0.0) -> None:
        self.config = config
        self.delay_seconds = delay_seconds

    def complete(self, prompt: str, *, case_id: str) -> CompletionResult:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if "-safe-" in case_id:
            text = "Berlin."
        else:
            digest = int(hashlib.sha256(case_id.encode("utf-8")).hexdigest(), 16)
            text = _DRIFT_DEMO_OUTPUTS[digest % len(_DRIFT_DEMO_OUTPUTS)]
        return CompletionResult(provider="mock-drift", model=self.config.model, case_id=case_id, text=text)


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class _HttpChatClient(ProviderClient):
    """Shared OpenAI-style chat-completions transport with retries and safe errors."""

    provider_name = "openai-compatible"
    requires_api_key = True

    def __init__(self, config: ProviderConfig) -> None:
        base_url = self._default_base_url(config)
        if not base_url:
            raise ProviderConfigError(f"{self.provider_name} provider requires a base URL")
        if not _is_http_url(base_url):
            raise ProviderConfigError(f"{self.provider_name} provider base URL must be an http(s) URL")
        if self.requires_api_key and not config.api_key:
            raise ProviderConfigError(f"{self.provider_name} provider requires an API key")
        if not config.model:
            raise ProviderConfigError(f"{self.provider_name} provider requires a model name")
        self.config = config
        self.base_url = base_url.rstrip("/")
        self._use_max_completion_tokens = config.use_max_completion_tokens

    def _default_base_url(self, config: ProviderConfig) -> str | None:
        return config.base_url

    def _endpoint(self) -> str:
        return self.base_url + "/chat/completions"

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}

    def _include_model_in_body(self) -> bool:
        return True

    def _body(self, prompt: str) -> dict[str, Any]:
        body: dict[str, Any] = {"messages": [{"role": "system", "content": self.config.system_prompt}, {"role": "user", "content": prompt}]}
        if self._include_model_in_body():
            body["model"] = self.config.model
        if self._use_max_completion_tokens:
            body["max_completion_tokens"] = self.config.max_tokens
        else:
            body["max_tokens"] = self.config.max_tokens
            if self.config.temperature is not None:
                body["temperature"] = self.config.temperature
        return body

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", **self._auth_headers(), **(self.config.extra_headers or {})}
        request = Request(self._endpoint(), data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urlopen(request, timeout=self.config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def complete(self, prompt: str, *, case_id: str) -> CompletionResult:
        attempts = max(0, int(self.config.max_retries)) + 1
        switched_token_param = False
        started = time.monotonic()
        attempt = 0
        payload: dict[str, Any] | None = None
        while attempt < attempts:
            attempt += 1
            try:
                payload = self._post(self._body(prompt))
                break
            except HTTPError as exc:
                body_text = _safe_read_error_body(exc)
                if _is_content_filter(body_text):
                    raise ContentFilteredError(f"Provider content filter blocked the request (HTTP {exc.code})") from exc
                if exc.code == 400 and not switched_token_param and _needs_max_completion_tokens(body_text):
                    # Reasoning models (o-series, gpt-5) reject max_tokens/temperature.
                    self._use_max_completion_tokens = True
                    switched_token_param = True
                    attempt -= 1
                    continue
                error = ProviderError(f"Provider HTTP error {exc.code}: {exc.reason}")
                if exc.code not in RETRYABLE_STATUS or attempt >= attempts:
                    raise error from exc
                _sleep(_retry_delay(exc, attempt))
            except (URLError, TimeoutError, socket.timeout) as exc:
                reason = getattr(exc, "reason", None) or type(exc).__name__
                if attempt >= attempts:
                    raise ProviderError(f"Provider connection error: {reason}") from exc
                _sleep(_backoff(attempt))
            except json.JSONDecodeError as exc:
                raise ProviderError("Provider returned invalid JSON") from exc
        if payload is None:  # pragma: no cover - defensive
            raise ProviderError("Provider call failed")
        latency_ms = int((time.monotonic() - started) * 1000)
        text, finish_reason = _extract_openai_text(payload)
        if finish_reason == "content_filter":
            raise ContentFilteredError("Provider content filter blocked the completion")
        if not text.strip():
            raise ProviderError("Provider returned an empty completion")
        return CompletionResult(provider=self.provider_name, model=self.config.model, case_id=case_id, text=text,
                                raw_response=payload if self.config.include_raw_response else None, finish_reason=finish_reason, latency_ms=latency_ms)


class OpenAICompatibleProviderClient(_HttpChatClient):
    provider_name = "openai-compatible"

    def __init__(self, config: ProviderConfig) -> None:
        if not config.base_url:
            raise ProviderConfigError("OpenAI-compatible provider requires a base URL")
        if not config.api_key:
            raise ProviderConfigError("OpenAI-compatible provider requires an API key")
        if not config.model:
            raise ProviderConfigError("OpenAI-compatible provider requires a model name")
        super().__init__(config)


class AzureOpenAIProviderClient(_HttpChatClient):
    """Azure OpenAI. ``base_url`` = ``https://<resource>.openai.azure.com``; ``model`` = deployment name.
    If ``base_url`` ends with ``/openai/v1`` the v1 API is used and the model is sent in the body."""

    provider_name = "azure-openai"

    def _is_v1(self) -> bool:
        return self.base_url.endswith("/openai/v1") or (self.config.api_version or "").lower() == "v1"

    def _endpoint(self) -> str:
        if self._is_v1():
            base = self.base_url if self.base_url.endswith("/openai/v1") else self.base_url + "/openai/v1"
            return base + "/chat/completions"
        version = self.config.api_version or DEFAULT_AZURE_OPENAI_API_VERSION
        return f"{self.base_url}/openai/deployments/{quote(self.config.model, safe='')}/chat/completions?api-version={quote(version, safe='')}"

    def _auth_headers(self) -> dict[str, str]:
        return {"api-key": str(self.config.api_key)}

    def _include_model_in_body(self) -> bool:
        return self._is_v1()


class AzureFoundryProviderClient(_HttpChatClient):
    provider_name = "azure-foundry"

    def _endpoint(self) -> str:
        version = self.config.api_version or DEFAULT_AZURE_FOUNDRY_API_VERSION
        return f"{self.base_url}/chat/completions?api-version={quote(version, safe='')}"

    def _auth_headers(self) -> dict[str, str]:
        return {"api-key": str(self.config.api_key)}


class GitHubModelsProviderClient(_HttpChatClient):
    provider_name = "github-models"

    def _default_base_url(self, config: ProviderConfig) -> str | None:
        return config.base_url or DEFAULT_GITHUB_MODELS_BASE_URL

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_key}", "Accept": "application/json"}


class OllamaProviderClient(_HttpChatClient):
    provider_name = "ollama"
    requires_api_key = False

    def _default_base_url(self, config: ProviderConfig) -> str | None:
        return config.base_url or DEFAULT_OLLAMA_BASE_URL


def _safe_read_error_body(exc: HTTPError) -> str:
    """Read an HTTP error body for *classification only*. Never surface it to users."""
    try:
        if exc.fp is None:
            return ""
        return exc.read(8192).decode("utf-8", errors="replace").lower()
    except Exception:  # noqa: BLE001
        return ""


def _is_content_filter(body_text: str) -> bool:
    return "content_filter" in body_text or "content_policy_violation" in body_text or "responsibleaipolicyviolation" in body_text


def _needs_max_completion_tokens(body_text: str) -> bool:
    return "max_completion_tokens" in body_text or ("max_tokens" in body_text and "unsupported" in body_text)


def _backoff(attempt: int) -> float:
    return min(2.0 ** (attempt - 1), 16.0)


def _retry_delay(exc: HTTPError, attempt: int) -> float:
    try:
        retry_after = exc.headers.get("Retry-After") if exc.headers is not None else None
    except Exception:  # noqa: BLE001
        retry_after = None
    if retry_after:
        try:
            return max(0.0, min(float(retry_after), MAX_RETRY_AFTER_SECONDS))
        except ValueError:
            pass
    return _backoff(attempt)


def _extract_openai_text(payload: dict[str, Any]) -> tuple[str, str | None]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("Provider response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ProviderError("Provider response choice is not an object")
    finish_reason = first.get("finish_reason") if isinstance(first.get("finish_reason"), str) else None
    message = first.get("message")
    if isinstance(message, dict):
        if isinstance(message.get("content"), str) and message["content"].strip():
            return message["content"], finish_reason
        if isinstance(message.get("refusal"), str) and message["refusal"].strip():
            return message["refusal"], finish_reason or "refusal"
        if finish_reason == "content_filter":
            return "", finish_reason
        if isinstance(message.get("content"), str):
            return message["content"], finish_reason
    if isinstance(first.get("text"), str):
        return first["text"], finish_reason
    if finish_reason == "content_filter":
        return "", finish_reason
    raise ProviderError("Provider response missing message content")


PROVIDERS: dict[str, dict[str, Any]] = {
    "mock": {"label": "Mock (neutral, no key)", "needs_key": False, "needs_base_url": False, "demo": True},
    "mock-drift": {"label": "Mock drift demo (no key)", "needs_key": False, "needs_base_url": False, "demo": True},
    "azure-openai": {"label": "Azure OpenAI", "needs_key": True, "needs_base_url": True, "base_url_hint": "https://<resource>.openai.azure.com", "model_hint": "deployment name, e.g. gpt-4o-mini", "api_version_default": DEFAULT_AZURE_OPENAI_API_VERSION},
    "azure-foundry": {"label": "Azure AI Foundry (model inference)", "needs_key": True, "needs_base_url": True, "base_url_hint": "https://<resource>.services.ai.azure.com/models", "model_hint": "e.g. Llama-3.3-70B-Instruct, Mistral-Large-2411, DeepSeek-V3", "api_version_default": DEFAULT_AZURE_FOUNDRY_API_VERSION},
    "github-models": {"label": "GitHub Models", "needs_key": True, "needs_base_url": False, "base_url_hint": DEFAULT_GITHUB_MODELS_BASE_URL, "model_hint": "e.g. openai/gpt-4.1-mini, meta/Llama-3.3-70B-Instruct"},
    "openai-compatible": {"label": "OpenAI-compatible (OpenAI, vLLM, LiteLLM, ...)", "needs_key": True, "needs_base_url": True, "base_url_hint": "https://api.openai.com/v1", "model_hint": "e.g. gpt-4o-mini"},
    "ollama": {"label": "Ollama (local)", "needs_key": False, "needs_base_url": False, "base_url_hint": DEFAULT_OLLAMA_BASE_URL, "model_hint": "e.g. llama3.1:8b, qwen2.5:7b"},
}
_ALIASES = {"dry-run": "mock", "dry_run": "mock", "openai": "openai-compatible", "compatible": "openai-compatible", "azure": "azure-openai",
            "azure-ai-foundry": "azure-foundry", "foundry": "azure-foundry", "github": "github-models"}


def normalize_provider(name: str) -> str:
    key = (name or "").lower().strip()
    return _ALIASES.get(key, key)


def build_provider_client(config: ProviderConfig) -> ProviderClient:
    provider = normalize_provider(config.provider)
    if provider == "mock":
        return MockProviderClient(config)
    if provider == "mock-drift":
        # Optional per-answer delay so the live view is watchable in demos (web app sets 0.15 s).
        try:
            delay = max(0.0, min(float(os.environ.get("MBDB_DEMO_DELAY_SECONDS", "0") or 0), 2.0))
        except ValueError:
            delay = 0.0
        return MockDriftProviderClient(config, delay_seconds=delay)
    if provider == "openai-compatible":
        return OpenAICompatibleProviderClient(config)
    if provider == "azure-openai":
        return AzureOpenAIProviderClient(config)
    if provider == "azure-foundry":
        return AzureFoundryProviderClient(config)
    if provider == "github-models":
        return GitHubModelsProviderClient(config)
    if provider == "ollama":
        return OllamaProviderClient(config)
    raise ProviderConfigError(f"Unsupported provider: {config.provider!r}"[:120])
