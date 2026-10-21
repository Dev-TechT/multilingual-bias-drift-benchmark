"""Provider clients: Azure OpenAI, Azure AI Foundry, GitHub Models, Ollama, http-json (own AI), python plugins, retries, content filter."""
import io
import json
import sys
import textwrap
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
    r = build_provider_client(ProviderConfig(provider="openai-compatible", base_url="https://api.example.test/v1", api_key="sk-test", model="m")).complete("P", case_id="c")
    assert calls[0]["url"] == "https://api.example.test/v1/chat/completions" and calls[0]["headers"]["authorization"] == "Bearer sk-test"
    assert r.text == "Cannot be determined." and r.raw_response is None


def test_azure_openai_deployment_url(monkeypatch):
    calls = capture(monkeypatch, [ok_payload()])
    build_provider_client(ProviderConfig(provider="azure-openai", model="gpt-4o-mini", base_url="https://res.openai.azure.com/", api_key="k1")).complete("P", case_id="c")
    assert calls[0]["url"] == "https://res.openai.azure.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=2024-10-21"
    assert calls[0]["headers"]["api-key"] == "k1" and "authorization" not in calls[0]["headers"] and "model" not in calls[0]["body"]


def test_azure_openai_v1_and_foundry(monkeypatch):
    calls = capture(monkeypatch, [ok_payload(), ok_payload()])
    build_provider_client(ProviderConfig(provider="azure", model="gpt-4.1", base_url="https://res.openai.azure.com/openai/v1", api_key="k")).complete("P", case_id="c")
    build_provider_client(ProviderConfig(provider="azure-foundry", model="Llama-3.3-70B-Instruct", base_url="https://res.services.ai.azure.com/models", api_key="k")).complete("P", case_id="c")
    assert calls[0]["url"] == "https://res.openai.azure.com/openai/v1/chat/completions" and calls[0]["body"]["model"] == "gpt-4.1"
    assert calls[1]["url"] == "https://res.services.ai.azure.com/models/chat/completions?api-version=2024-05-01-preview"


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


def test_retries_then_success_and_no_body_leak(monkeypatch):
    calls = capture(monkeypatch, [http_error(429, headers={"Retry-After": "1"}), http_error(503), ok_payload("Fine.")])
    assert build_provider_client(ProviderConfig(provider="openai", model="m", base_url="https://x.test/v1", api_key="k")).complete("P", case_id="c").text == "Fine."
    assert len(calls) == 3
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


def test_reasoning_model_switch_rebuilds_body(monkeypatch):
    calls = capture(monkeypatch, [http_error(400, b"Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens' instead."), ok_payload()])
    build_provider_client(ProviderConfig(provider="openai", model="o4-mini", base_url="https://x.test/v1", api_key="k")).complete("P", case_id="c")
    assert "max_tokens" in calls[0]["body"] and "max_completion_tokens" in calls[1]["body"] and "temperature" not in calls[1]["body"]


def test_structured_refusal(monkeypatch):
    capture(monkeypatch, [{"choices": [{"message": {"content": None, "refusal": "I can't help with that."}, "finish_reason": "stop"}]}])
    assert build_provider_client(ProviderConfig(provider="openai", model="m", base_url="https://x.test/v1", api_key="k")).complete("P", case_id="c").text == "I can't help with that."


def test_http_json_own_ai_contract(monkeypatch):
    calls = capture(monkeypatch, [{"text": "Not enough information."}, {"text": "", "refused": True}, {"text": "", "content_filtered": True}, {"oops": 1}])
    client = build_provider_client(ProviderConfig(provider="http-json", model="", base_url="https://my-ai.test/generate", api_key="secret"))
    assert client.complete("Prompt X", case_id="fitb-en-a-001").text == "Not enough information."
    body = calls[0]["body"]
    assert calls[0]["url"] == "https://my-ai.test/generate" and calls[0]["headers"]["authorization"] == "Bearer secret"
    assert body["schema"] == "mbdb.generate.v1" and body["case_id"] == "fitb-en-a-001" and body["prompt"] == "Prompt X" and body["model"] == "custom"
    assert client.complete("P", case_id="c").text == "I cannot help with that."
    with pytest.raises(ContentFilteredError):
        client.complete("P", case_id="c")
    with pytest.raises(ProviderError, match="text"):
        client.complete("P", case_id="c")


def test_http_json_needs_url():
    with pytest.raises(ProviderError, match="base URL"):
        build_provider_client(ProviderConfig(provider="custom", model="m"))


def test_python_plugin_provider(tmp_path, monkeypatch):
    (tmp_path / "my_test_plugin.py").write_text(textwrap.dedent('''
        from fillblank_eval.provider_client import CompletionResult, ProviderClient
        class Model(ProviderClient):
            def __init__(self, config): self.config = config
            def complete(self, prompt, *, case_id): return CompletionResult("plugin", self.config.model, case_id, "plugin answer")
    '''), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    client = build_provider_client(ProviderConfig(provider="python:my_test_plugin:Model", model="x"))
    assert client.complete("P", case_id="c").text == "plugin answer"
    with pytest.raises(ProviderError, match="cannot load"):
        build_provider_client(ProviderConfig(provider="python:nope_module:Model", model="x"))
    sys.modules.pop("my_test_plugin", None)


def test_mock_drift_deterministic_and_delay_env(monkeypatch):
    client = build_provider_client(ProviderConfig(provider="mock-drift", model="demo"))
    assert client.complete("P", case_id="fitb-en-x-001").text == client.complete("P", case_id="fitb-en-x-001").text
    assert client.complete("P", case_id="fitb-de-c24-20-safe-meeting").text == "Berlin."
    monkeypatch.setenv("MBDB_DEMO_DELAY_SECONDS", "0.25")
    assert build_provider_client(ProviderConfig(provider="mock-drift", model="d")).delay_seconds == 0.25
    monkeypatch.setenv("MBDB_DEMO_DELAY_SECONDS", "abc")
    assert build_provider_client(ProviderConfig(provider="mock-drift", model="d")).delay_seconds == 0.0


def test_unknown_provider_and_roles():
    with pytest.raises(ProviderError, match="Unsupported"):
        build_provider_client(ProviderConfig(provider="nope", model="m"))
    assert pc.PROVIDERS["http-judge"]["role"] == "judge" and pc.PROVIDERS["mock"]["role"] == "target" and pc.PROVIDERS["azure-openai"]["role"] == "both"
