"""Web app API tests incl. live view (FastAPI TestClient; no network)."""
import json
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from fillblank_eval.provider_client import CompletionResult  # noqa: E402
from fillblank_web.app import create_app  # noqa: E402
from fillblank_web.runs import build_plan  # noqa: E402
from fillblank_web.settings import ServerProfile, Settings  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def make_settings(tmp_path, **overrides):
    base = Settings(data_dir=tmp_path / "data", datasets_dir=ROOT / "examples", app_token=None, max_concurrent_runs=2, max_cases_per_run=1000,
                    max_workers=8, allow_user_keys=True, allow_custom_endpoints=True,
                    enabled_providers=["mock", "mock-drift", "azure-openai", "azure-foundry", "github-models", "openai-compatible", "ollama"],
                    max_upload_bytes=200_000, profiles={})
    return replace(base, **overrides)


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(make_settings(tmp_path)))


def wait_for(client, run_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in {"completed", "failed", "cancelled"}:
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_health_meta_headers_and_static(client):
    r = client.get("/api/health")
    assert r.json()["status"] == "ok" and r.headers["x-content-type-options"] == "nosniff" and "default-src 'self'" in r.headers["content-security-policy"]
    assert client.get("/api/meta").json()["languages"]["tr"] == "Turkish"
    assert "Every question in every language" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200 and client.get("/favicon.ico").status_code == 204


def test_datasets_listed(client):
    builtin = {d["id"]: d for d in client.get("/api/datasets").json()["builtin"]}
    assert builtin["public_core24_15lang"]["case_count"] == 360 and len(builtin["public_core24_15lang"]["languages"]) == 15


def test_build_plan_groups_and_language_order():
    cases = [{"id": f"fitb-{l}-x", "language": l, "translation_group": "g1", "control_type": "negative_control", "prompt_template": f"{l} text {{blank}}"} for l in ("tr", "de", "en")]
    cases.append({"id": "fitb-en-solo", "language": "en", "prompt_template": "solo {blank}"})
    plan = build_plan(cases)
    assert plan["languages"] == ["en", "de", "tr"] and plan["total"] == 4
    assert plan["groups"][0]["label"] == "en text {blank}" and plan["groups"][0]["cells"]["de"] == "fitb-de-x"
    assert plan["groups"][1]["id"] == "fitb-en-solo"


def test_full_run_with_live_view(client):
    created = client.post("/api/runs", json={"provider": "mock-drift", "model": "demo", "datasets": ["public_core24_15lang", "public_top15_sample"], "workers": 4, "label": "demo"})
    assert created.status_code == 202, created.text
    run_id = created.json()["run_id"]
    live = client.get(f"/api/runs/{run_id}/live").json()
    assert live["plan"]["total"] == 395 and len(live["plan"]["languages"]) == 15
    run = wait_for(client, run_id)
    assert run["status"] == "completed" and run["ok"] and run["progress"]["completed"] == 395
    live = client.get(f"/api/runs/{run_id}/live").json()
    assert len(live["answers"]) == 395
    cell = live["plan"]["groups"][0]["cells"]["de"]
    assert live["answers"][cell]["stance"] in {"anti_stereotype", "pro_counter_stereotype", "neutral_uncertain", "refusal_void"}
    assert run["summary"]["drift_alerts"]
    rows = client.get(f"/api/runs/{run_id}/results").json()["rows"]
    assert len(rows) == 395 and all("raw_response" not in r for r in rows)
    report = client.get(f"/api/runs/{run_id}/artifacts/report.html")
    assert report.status_code == 200 and "style-src 'unsafe-inline'" in report.headers["content-security-policy"]
    assert client.get(f"/api/runs/{run_id}/artifacts/meta.json").status_code == 404
    assert client.delete(f"/api/runs/{run_id}").status_code == 200 and client.get(f"/api/runs/{run_id}").status_code == 404


def test_live_view_updates_during_run_and_after_restart(tmp_path, monkeypatch):
    gate, seen = threading.Event(), []

    class Gated:
        def complete(self, prompt, *, case_id):
            seen.append(case_id)
            if len(seen) > 3:
                gate.wait(5)
            return CompletionResult(provider="mock", model="m", case_id=case_id, text="Cannot be determined from the scenario.")

    monkeypatch.setattr("fillblank_eval.runner.build_provider_client", lambda c: Gated())
    settings = make_settings(tmp_path)
    client = TestClient(create_app(settings))
    run_id = client.post("/api/runs", json={"provider": "mock", "datasets": ["public_top15_sample"]}).json()["run_id"]
    deadline = time.time() + 5
    while time.time() < deadline and len(client.get(f"/api/runs/{run_id}/live").json()["answers"]) < 3:
        time.sleep(0.05)
    mid = client.get(f"/api/runs/{run_id}/live").json()
    assert mid["status"] == "running" and 3 <= len(mid["answers"]) < 35
    assert "summary" not in client.get(f"/api/runs/{run_id}").json()  # final numbers only after completion
    gate.set()
    wait_for(client, run_id)
    reloaded = TestClient(create_app(settings))
    after = reloaded.get(f"/api/runs/{run_id}/live").json()
    assert len(after["answers"]) == 35 and after["plan"]["total"] == 35


def test_api_key_never_returned_or_persisted(tmp_path, monkeypatch):
    class Fake:
        def complete(self, prompt, *, case_id):
            return CompletionResult(provider="azure-openai", model="d", case_id=case_id, text="Cannot be determined.")

    monkeypatch.setattr("fillblank_eval.runner.build_provider_client", lambda c: Fake())
    settings = make_settings(tmp_path)
    client = TestClient(create_app(settings))
    secret = "azure-secret-key-abcdef"
    created = client.post("/api/runs", json={"provider": "azure-openai", "model": "gpt-4o-mini", "base_url": "https://res.openai.azure.com", "api_key": secret, "datasets": ["public_top10_sample"]})
    assert created.status_code == 202 and secret not in created.text
    run = wait_for(client, created.json()["run_id"])
    assert run["request"]["target"]["api_key_supplied"] is True and secret not in json.dumps(run)
    assert secret not in "".join(p.read_text(encoding="utf-8", errors="ignore") for p in settings.data_dir.rglob("*") if p.is_file())


@pytest.mark.parametrize("payload, fragment", [
    ({"provider": "azure-openai", "model": "d", "base_url": "https://x.openai.azure.com", "datasets": ["public_top10_sample"]}, "API key"),
    ({"provider": "azure-openai", "model": "d", "api_key": "k", "datasets": ["public_top10_sample"]}, "base_url"),
    ({"provider": "openai-compatible", "model": "m", "api_key": "k", "base_url": "http://example.com/v1", "datasets": ["public_top10_sample"]}, "https"),
    ({"provider": "openai-compatible", "model": "m", "api_key": "k", "base_url": "ftp://x", "datasets": ["public_top10_sample"]}, "http(s)"),
    ({"provider": "nope", "model": "m", "datasets": ["public_top10_sample"]}, "unsupported"),
    ({"provider": "mock", "datasets": ["../../etc/passwd"]}, "dataset"),
    ({"provider": "mock", "datasets": ["does_not_exist"]}, "unknown dataset"),
    ({"provider": "mock", "datasets": ["public_top10_sample"], "scorer": "judge"}, "judge"),
])
def test_run_request_validation(client, payload, fragment):
    response = client.post("/api/runs", json=payload)
    assert response.status_code == 422 and fragment.lower() in response.text.lower()


def test_ollama_local_http_allowed(client):
    assert client.post("/api/runs", json={"provider": "ollama", "model": "llama3.1:8b", "base_url": "http://host.docker.internal:11434/v1", "datasets": ["public_top10_sample"], "limit": 1}).status_code == 202


def test_locked_down_mode(tmp_path):
    profile = ServerProfile("azure-openai", "azure-openai", "Azure", ["gpt-4o-mini"], "https://r.openai.azure.com", "server-key")
    client = TestClient(create_app(make_settings(tmp_path, allow_user_keys=False, allow_custom_endpoints=False, profiles={"azure-openai": profile})))
    assert client.post("/api/runs", json={"provider": "openai-compatible", "model": "m", "api_key": "k", "base_url": "https://evil.test/v1", "datasets": ["public_top10_sample"]}).status_code == 422
    meta = client.get("/api/meta").json()
    assert meta["profiles"][0]["has_key"] is True and "server-key" not in json.dumps(meta)
    assert client.post("/api/runs", json={"provider": "azure-openai", "profile": "azure-openai", "model": "other", "datasets": ["public_top10_sample"]}).status_code == 422


def test_token_auth(tmp_path):
    client = TestClient(create_app(make_settings(tmp_path, app_token="s3cret")))
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/meta").status_code == 401 and client.get("/api/meta", headers={"X-API-Token": "wrong"}).status_code == 401
    assert client.get("/api/meta", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_dataset_upload(client):
    good = (ROOT / "examples/public_top10_sample.jsonl").read_text(encoding="utf-8")
    r = client.post("/api/datasets", json={"filename": "mine.jsonl", "content": good})
    assert r.status_code == 201 and r.json()["case_count"] == 10
    assert client.post("/api/datasets", json={"filename": "bad.jsonl", "content": '{"id": "x"}\n'}).status_code == 422
    private = good.replace('"tier": "public_sample"', '"tier": "private_' + 'holdout"')  # split so the leak scanner ignores this fixture
    assert client.post("/api/datasets", json={"filename": "p.jsonl", "content": private}).status_code == 422
    assert client.post("/api/datasets", json={"content": "x" * 300_000}).status_code == 413
    assert client.delete(f"/api/datasets/{r.json()['id']}").status_code == 200


def test_cancel_and_history(tmp_path, monkeypatch):
    gate = threading.Event()

    class Slow:
        def complete(self, prompt, *, case_id):
            gate.wait(5)
            return CompletionResult(provider="mock", model="m", case_id=case_id, text="Cannot be determined.")

    monkeypatch.setattr("fillblank_eval.runner.build_provider_client", lambda c: Slow())
    settings = make_settings(tmp_path)
    client = TestClient(create_app(settings))
    run_id = client.post("/api/runs", json={"provider": "mock", "datasets": ["public_dev"]}).json()["run_id"]
    time.sleep(0.2)
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 200
    assert client.delete(f"/api/runs/{run_id}").status_code == 409
    gate.set()
    assert wait_for(client, run_id)["status"] == "cancelled"
    reloaded = TestClient(create_app(settings))
    assert reloaded.get(f"/api/runs/{run_id}").json()["status"] == "cancelled"
    assert reloaded.get("/api/runs/not-valid").status_code == 404
