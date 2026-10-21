"""Provider clients ("the model under test").

Built-in providers (``ProviderConfig.provider``):

- ``mock`` / ``dry-run``: credential-free, always neutral. Pipeline smoke test only.
- ``mock-drift``: credential-free demo with deliberate cross-language drift. Never use as model evidence.
- ``openai-compatible`` / ``openai``: any OpenAI-style ``/chat/completions`` endpoint (Bearer auth).
- ``azure-openai``: Azure OpenAI deployment (or ``/openai/v1``) endpoint, ``api-key`` header.
- ``azure-foundry``: Azure AI Foundry model inference (``.../models``), ``api-key`` header.
- ``github-models``: GitHub Models (``https://models.github.ai/inference``), PAT with ``models:read``.
- ``ollama``: local Ollama OpenAI-compatible API, no key.
- ``http-json``: **your own AI** behind a tiny JSON contract (``mbdb.generate.v1``), see docs/CUSTOM_AI.md.
- ``python:<module>:<Class>``: **your own AI** as a Python class (CLI only; disabled in the web app).

All HTTP providers share retry/backoff for 408/409/429/5xx/timeouts, never echo response bodies in
errors, and map content-filter blocks to :class:`ContentFilteredError`.
"""
from __future__ import annotations

import hashlib
import importlib
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
GENERATE_SCHEMA = "mbdb.generate.v1"
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
MAX_RETRY_AFTER_SECONDS = 30.0

_sleep: Callable[[float], None] = time.sleep  # indirection so tests can avoid real sleeping


class ProviderError(RuntimeError):
    """Raised when a provider cannot be configured or called safely."""


class ProviderConfigError(ProviderError):
    """Local configuration problem (missing key/URL/model). Messages are constant text, safe to show."""


class ContentFilteredError(ProviderError):
    """The provider's safety filter blocked the prompt or completion (recorded as ``refusal_void``)."""


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
    """Interface for all providers. Implement ``complete`` to plug in your own AI (docs/CUSTOM_AI.md)."""

    def complete(self, prompt: str, *, case_id: str) -> CompletionResult:
        raise NotImplementedError


class MockProviderClient(ProviderClient):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def complete(self, prompt: str, *, case_id: str) -> CompletionResult:
        return CompletionResult(provider="mock", model=self.config.model, case_id=case_id, text="The scenario does not provide enough information to determine the blank.")


_DRIFT_DEMO_OUTPUTS = (
    "The scenario does not provide enough information to determine that.",
    "We should not assume age or gender here; stereotypes are not supported by the scenario.",
    "It must have been the older person, obviously.",
    "I cannot answer any question about this topic.",
)


class MockDriftProviderClient(ProviderClient):
    """Deterministic synthetic demo: answer depends on a hash of the case id; positive controls get a direct answer."""

    def __init__(self, config: ProviderConfig, delay_seconds: float = 0.0) -> None:
        self.config = config
        self.delay_seconds = delay_seconds

    def complete(self, prompt: str, *, case_id: str) -> CompletionResult:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if "-safe-" in case_id:
            text = "Berlin."
        else:
            text = _DRIFT_DEMO_OUTPUTS[int(hashlib.sha256(case_id.encode("utf-8")).hexdigest(), 16) % len(_DRIFT_DEMO_OUTPUTS)]
        return CompletionResult(provider="mock-drift", model=self.config.model, case_id=case_id, text=text)


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def post_json_with_retries(url: str, body: "dict[str, Any] | Callable[[], dict[str, Any]]", headers: dict[str, str], *, timeout: int, max_retries: int,
                           on_bad_request: Callable[[str], bool] | None = None) -> dict[str, Any]:
    """POST JSON with retries. Never surfaces response bodies. ``on_bad_request(body_text)`` may return True to retry once."""
    attempts = max(0, int(max_retries)) + 1
    attempt = 0
    retried_400 = False
    while True:
        attempt += 1
        request = Request(url, data=json.dumps(body() if callable(body) else body).encode("utf-8"), headers={"Content-Type": "application/json", **headers}, method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body_text = _safe_read_error_body(exc)
            if _is_content_filter(body_text):
                raise ContentFilteredError(f"Provider content filter blocked the request (HTTP {exc.code})") from exc
            if exc.code == 400 and on_bad_request is not None and not retried_400 and on_bad_request(body_text):
                retried_400 = True
                attempt -= 1
                continue
            if exc.code not in RETRYABLE_STATUS or attempt >= attempts:
                raise ProviderError(f"Provider HTTP error {exc.code}: {exc.reason}") from exc
            _sleep(_retry_delay(exc, attempt))
        except (URLError, TimeoutError, socket.timeout) as exc:
            if attempt >= attempts:
                raise ProviderError(f"Provider connection error: {getattr(exc, 'reason', None) or type(exc).__name__}") from exc
            _sleep(_backoff(attempt))
        except json.JSONDecodeError as exc:
            raise ProviderError("Provider returned invalid JSON") from exc


class _HttpChatClient(ProviderClient):
    """Shared OpenAI-style chat-completions transport."""

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

    def _body(self, prompt: str, case_id: str) -> dict[str, Any]:
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

    def _on_bad_request(self, body_text: str) -> bool:
        # Reasoning models (o-series, gpt-5) reject max_tokens/temperature.
        if not self._use_max_completion_tokens and _needs_max_completion_tokens(body_text):
            self._use_max_completion_tokens = True
            return True
        return False

    def _extract(self, payload: dict[str, Any]) -> tuple[str, str | None]:
        return _extract_openai_text(payload)

    def complete(self, prompt: str, *, case_id: str) -> CompletionResult:
        started = time.monotonic()
        headers = {**self._auth_headers(), **(self.config.extra_headers or {})}
        payload = post_json_with_retries(self._endpoint(), lambda: self._body(prompt, case_id), headers, timeout=self.config.timeout_seconds,
                                         max_retries=self.config.max_retries, on_bad_request=self._on_bad_request)
        text, finish_reason = self._extract(payload)
        if finish_reason == "content_filter":
            raise ContentFilteredError("Provider content filter blocked the completion")
        if not text.strip():
            raise ProviderError("Provider returned an empty completion")
        return CompletionResult(provider=self.provider_name, model=self.config.model, case_id=case_id, text=text,
                                raw_response=payload if self.config.include_raw_response else None, finish_reason=finish_reason,
                                latency_ms=int((time.monotonic() - started) * 1000))


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
        return f"{self.base_url}/chat/completions?api-version={quote(self.config.api_version or DEFAULT_AZURE_FOUNDRY_API_VERSION, safe='')}"

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


class HttpJsonProviderClient(_HttpChatClient):
    """Your own AI behind the ``mbdb.generate.v1`` JSON contract (docs/CUSTOM_AI.md).

    Request:  POST <base_url>  {"schema": "mbdb.generate.v1", "case_id", "model", "prompt", "system_prompt", "max_tokens", "temperature"}
    Response: {"text": "..."}  optional: {"refused": true} or {"content_filtered": true}
    Auth:     ``Authorization: Bearer <api_key>`` if a key is set.
    """

    provider_name = "http-json"
    requires_api_key = False

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config if config.model else ProviderConfig(**{**config.__dict__, "model": "custom"}))

    def _endpoint(self) -> str:
        return self.base_url

    def _body(self, prompt: str, case_id: str) -> dict[str, Any]:
        return {"schema": GENERATE_SCHEMA, "case_id": case_id, "model": self.config.model, "prompt": prompt,
                "system_prompt": self.config.system_prompt, "max_tokens": self.config.max_tokens, "temperature": self.config.temperature}

    def _on_bad_request(self, body_text: str) -> bool:
        return False

    def _extract(self, payload: dict[str, Any]) -> tuple[str, str | None]:
        if not isinstance(payload, dict):
            raise ProviderError("http-json provider returned a non-object response")
        if payload.get("content_filtered") is True:
            return "", "content_filter"
        text = payload.get("text")
        if not isinstance(text, str):
            raise ProviderError("http-json provider response is missing the string field 'text'")
        if payload.get("refused") is True and not text.strip():
            return "I cannot help with that.", "refusal"
        return text, payload.get("finish_reason") if isinstance(payload.get("finish_reason"), str) else None


def load_python_provider(spec: str, config: ProviderConfig) -> ProviderClient:
    """Load ``python:<module>:<Class>``. The class gets the ProviderConfig and must implement ``complete``."""
    try:
        _, module_name, class_name = spec.split(":", 2)
    except ValueError as exc:
        raise ProviderConfigError("python provider must look like python:<module>:<Class>") from exc
    try:
        cls = getattr(importlib.import_module(module_name), class_name)
    except (ImportError, AttributeError) as exc:
        raise ProviderConfigError(f"cannot load python provider {module_name}:{class_name}") from exc
    client = cls(config)
    if not callable(getattr(client, "complete", None)):
        raise ProviderConfigError(f"python provider {class_name} has no complete(prompt, *, case_id) method")
    return client


def _safe_read_error_body(exc: HTTPError) -> str:
    """Read an HTTP error body for *classification only*. Never surface it to users."""
    try:
        return "" if exc.fp is None else exc.read(8192).decode("utf-8", errors="replace").lower()
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
    "azure-foundry": {"label": "Azure AI Foundry (model inference)", "needs_key": True, "needs_base_url": True, "base_url_hint": "https://<resource>.services.ai.azure.com/models", "model_hint": "e.g. Llama-3.3-70B-Instruct, Mistral-Large-2411", "api_version_default": DEFAULT_AZURE_FOUNDRY_API_VERSION},
    "github-models": {"label": "GitHub Models", "needs_key": True, "needs_base_url": False, "base_url_hint": DEFAULT_GITHUB_MODELS_BASE_URL, "model_hint": "e.g. openai/gpt-4.1-mini"},
    "openai-compatible": {"label": "OpenAI-compatible (OpenAI, vLLM, LiteLLM, ...)", "needs_key": True, "needs_base_url": True, "base_url_hint": "https://api.openai.com/v1", "model_hint": "e.g. gpt-4o-mini"},
    "ollama": {"label": "Ollama (local)", "needs_key": False, "needs_base_url": False, "base_url_hint": DEFAULT_OLLAMA_BASE_URL, "model_hint": "e.g. llama3.1:8b"},
    "http-json": {"label": "Your own AI (HTTP JSON contract)", "needs_key": False, "needs_base_url": True, "base_url_hint": "https://my-ai.example.com/mbdb/generate", "model_hint": "optional label", "role": "target"},
    "http-judge": {"label": "External judge (HTTP JSON, e.g. Jev relay)", "needs_key": False, "needs_base_url": True, "base_url_hint": "https://my-judge.example.com/mbdb/judge", "model_hint": "optional label", "role": "judge"},
}
for _info in PROVIDERS.values():
    _info.setdefault("role", "target" if _info.get("demo") else "both")
_ALIASES = {"dry-run": "mock", "dry_run": "mock", "openai": "openai-compatible", "compatible": "openai-compatible", "azure": "azure-openai",
            "azure-ai-foundry": "azure-foundry", "foundry": "azure-foundry", "github": "github-models", "custom": "http-json"}


def normalize_provider(name: str) -> str:
    key = (name or "").strip()
    if key.lower().startswith("python:"):
        return key
    return _ALIASES.get(key.lower(), key.lower())


def build_provider_client(config: ProviderConfig) -> ProviderClient:
    provider = normalize_provider(config.provider)
    if provider.startswith("python:"):
        return load_python_provider(provider, config)
    if provider == "mock":
        return MockProviderClient(config)
    if provider == "mock-drift":
        try:
            delay = max(0.0, min(float(os.environ.get("MBDB_DEMO_DELAY_SECONDS", "0") or 0), 2.0))
        except ValueError:
            delay = 0.0
        return MockDriftProviderClient(config, delay_seconds=delay)
    clients = {"openai-compatible": OpenAICompatibleProviderClient, "azure-openai": AzureOpenAIProviderClient, "azure-foundry": AzureFoundryProviderClient,
               "github-models": GitHubModelsProviderClient, "ollama": OllamaProviderClient, "http-json": HttpJsonProviderClient}
    if provider in clients:
        return clients[provider](config)
    raise ProviderConfigError(f"Unsupported provider: {config.provider!r}"[:120])
