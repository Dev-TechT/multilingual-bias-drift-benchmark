"""Provider clients: Azure OpenAI, Azure AI Foundry, GitHub Models, Ollama, retries, content filter."""
import io
import json
from email.message import Message
from urllib.error import HTTPError, URLError

import pytest

from fillblank_eval import provider_client as pc
from fillblank_eval.provider_client import ContentFilteredError, ProviderConfig, ProviderError, build_provider_client


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def ok_payload(text="Cannot be determined.", finish_reason="stop"):
    return {"choices": [{"message": {"content": text}, "finish_reason": finish_reason}]}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(pc, "_sleep", lambda seconds: None)


def capture(monkeypatch, responses):
    calls, queue = [], list(responses)

    def fake_urlopen(request, timeout):
        calls.append({"url": request.full_url, "headers": {k.lower(): v for k, v in request.header_items()}, "body": json.loads(request.data.decode())})
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)

    monkeypatch.setattr(pc, "urlopen", fake_urlopen)
    return calls


def http_error(code, body=b"", headers=None):
    hdrs = Message()
    for key, value in (headers or {}).items():
        hdrs[key] = value
    return HTTPError("https://x.test", code, "err", hdrs=hdrs, fp=io.BytesIO(body))


def test_openai_compatible_basic(monkeypatch):
    calls = capture(monkeypatch, [ok_payload()])
    r = build_provider_client(ProviderConfig(provider="openai-compatible", base_url="https://api.example.test/v1", api_key="sk-test", model="m", timeout_seconds=7)).complete("P", case_id="c")
    assert calls[0]["url"] == "https://api.example.test/v1/chat/completions" and calls[0]["headers"]["authorization"] == "Bearer sk-test"
    assert "preserve uncertainty" not in calls[0]["body"]["messages"][0]["content"].lower()
    assert r.text == "Cannot be determined." and r.raw_response is None


def test_azure_openai_deployment_url(monkeypatch):
    calls = capture(monkeypatch, [ok_payload()])
    build_provider_client(ProviderConfig(provider="azure-openai", model="gpt-4o-mini", base_url="https://res.openai.azure.com/", api_key="k1")).complete("P", case_id="c")
    assert calls[0]["url"] == "https://res.openai.azure.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=2024-10-21"
    assert calls[0]["headers"]["api-key"] == "k1" and "authorization" not in calls[0]["headers"] and "model" not in calls[0]["body"]


def test_azure_openai_v1(monkeypatch):
    calls = capture(monkeypatch, [ok_payload()])
    build_provider_client(ProviderConfig(provider="azure", model="gpt-4.1", base_url="https://res.openai.azure.com/openai/v1", api_key="k")).complete("P", case_id="c")
    assert calls[0]["url"] == "https://res.openai.azure.com/openai/v1/chat/completions" and calls[0]["body"]["model"] == "gpt-4.1"


def test_azure_foundry(monkeypatch):
    calls = capture(monkeypatch, [ok_payload()])
    build_provider_client(ProviderConfig(provider="azure-foundry", model="Llama-3.3-70B-Instruct", base_url="https://res.services.ai.azure.com/models", api_key="k")).complete("P", case_id="c")
    assert calls[0]["url"] == "https://res.services.ai.azure.com/models/chat/completions?api-version=2024-05-01-preview" and calls[0]["body"]["model"] == "Llama-3.3-70B-Instruct"


def test_github_models_and_ollama(monkeypatch):
    calls = capture(monkeypatch, [ok_payload(), ok_payload()])
    build_provider_client(ProviderConfig(provider="github-models", model="openai/gpt-4.1-mini", api_key="ghp_x")).complete("P", case_id="c")
    build_provider_client(ProviderConfig(provider="ollama", model="llama3.1:8b")).complete("P", case_id="c")
    assert calls[0]["url"] == "https://models.github.ai/inference/chat/completions" and calls[0]["headers"]["authorization"] == "Bearer ghp_x"
    assert calls[1]["url"] == "http://localhost:11434/v1/chat/completions" and "authorization" not in calls[1]["headers"]


@pytest.mark.parametrize("provider", ["azure-openai", "azure-foundry", "openai-compatible"])
def test_http_providers_require_key(provider):
    with pytest.raises(ProviderError, match="API key"):
        build_provider_client(ProviderConfig(provider=provider, model="m", base_url="https://x.test"))


def test_non_http_base_url_rejected():
    with pytest.raises(ProviderError, match="http"):
        build_provider_client(ProviderConfig(provider="ollama", model="m", base_url="file:///etc/passwd"))


def test_retries_then_success(monkeypatch):
    calls = capture(monkeypatch, [http_error(429, headers={"Retry-After": "1"}), http_error(503), ok_payload("Fine.")])
    assert build_provider_client(ProviderConfig(provider="openai", model="m", base_url="https://x.test/v1", api_key="k")).complete("P", case_id="c").text == "Fine."
    assert len(calls) == 3


def test_retries_exhausted_no_body_leak(monkeypatch):
    capture(monkeypatch, [http_error(500, b'{"secret":"sk-leak"}')] * 3)
    with pytest.raises(ProviderError) as info:
        build_provider_client(ProviderConfig(provider="openai", model="m", base_url="https://x.test/v1", api_key="k", max_retries=2)).complete("P", case_id="c")
    assert "500" in str(info.value) and "sk-leak" not in str(info.value)


def test_connection_error_retried_and_400_not(monkeypatch):
    calls = capture(monkeypatch, [URLError("refused"), ok_payload(), http_error(400, b"bad")])
    build_provider_client(ProviderConfig(provider="ollama", model="m", max_retries=1)).complete("P", case_id="c")
    with pytest.raises(ProviderError, match="400"):
        build_provider_client(ProviderConfig(provider="openai", model="m", base_url="https://x.test/v1", api_key="k")).complete("P", case_id="c")
    assert len(calls) == 3


def test_content_filter_mapping(monkeypatch):
    capture(monkeypatch, [http_error(400, b'{"error":{"code":"content_filter"}}'), {"choices": [{"message": {"content": None}, "finish_reason": "content_filter"}]}])
    client = build_provider_client(ProviderConfig(provider="azure-openai", model="d", base_url="https://r.openai.azure.com", api_key="k"))
    for _ in range(2):
        with pytest.raises(ContentFilteredError):
            client.complete("P", case_id="c")


def test_reasoning_model_switch(monkeypatch):
    calls = capture(monkeypatch, [http_error(400, b"Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens' instead."), ok_payload()])
    build_provider_client(ProviderConfig(provider="openai", model="o4-mini", base_url="https://x.test/v1", api_key="k")).complete("P", case_id="c")
    assert "max_completion_tokens" in calls[1]["body"] and "temperature" not in calls[1]["body"]


def test_structured_refusal(monkeypatch):
    capture(monkeypatch, [{"choices": [{"message": {"content": None, "refusal": "I can't help with that."}, "finish_reason": "stop"}]}])
    assert build_provider_client(ProviderConfig(provider="openai", model="m", base_url="https://x.test/v1", api_key="k")).complete("P", case_id="c").text == "I can't help with that."


def test_mock_drift_deterministic_and_delay_env(monkeypatch):
    client = build_provider_client(ProviderConfig(provider="mock-drift", model="demo"))
    assert client.complete("P", case_id="fitb-en-x-001").text == client.complete("P", case_id="fitb-en-x-001").text
    assert client.complete("P", case_id="fitb-de-c24-20-safe-meeting").text == "Berlin."
    monkeypatch.setenv("MBDB_DEMO_DELAY_SECONDS", "0.25")
    assert build_provider_client(ProviderConfig(provider="mock-drift", model="d")).delay_seconds == 0.25
    monkeypatch.setenv("MBDB_DEMO_DELAY_SECONDS", "abc")
    assert build_provider_client(ProviderConfig(provider="mock-drift", model="d")).delay_seconds == 0.0


def test_unknown_provider():
    with pytest.raises(ProviderError, match="Unsupported"):
        build_provider_client(ProviderConfig(provider="nope", model="m"))
