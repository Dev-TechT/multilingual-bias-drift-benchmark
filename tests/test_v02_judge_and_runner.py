"""Judges (LLM + external HTTP judge with confidence), content filter, workers, cancellation, metadata, drift alerts, own AI end-to-end."""
import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from fillblank_eval import provider_client as pc
from fillblank_eval.judge import HttpJsonJudge, build_judge_request, parse_judge_reply, verdict_from_object
from fillblank_eval.provider_client import CompletionResult, ContentFilteredError, ProviderError
from fillblank_eval.runner import RunnerConfig, run_benchmark
from tests.test_validator import base_case

ROOT = Path(__file__).resolve().parents[1]


def case(case_id, language="en", group=None, control="negative_control"):
    row = base_case(id=case_id, language=language, control_type=control, tier="public_dev", prompt_template=f"Scenario {case_id}: the person was {{blank}}.")
    if group:
        row["translation_group"] = group
    return row


def write(tmp_path, rows):
    path = tmp_path / "public_dev.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


class ScriptedClient:
    def __init__(self, outputs):
        self.outputs, self.lock, self.calls = outputs, threading.Lock(), []

    def complete(self, prompt, *, case_id):
        with self.lock:
            self.calls.append(case_id)
        value = self.outputs[case_id] if isinstance(self.outputs, dict) else self.outputs(case_id, prompt)
        if isinstance(value, Exception):
            raise value
        return CompletionResult(provider="scripted", model="m", case_id=case_id, text=value)


def read_rows(out):
    return [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]


def read_summary(out):
    return json.loads((out / "summary.json").read_text(encoding="utf-8"))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def server():
    procs = []

    def start(script, port, env=None):
        import os
        proc = subprocess.Popen([sys.executable, str(ROOT / "examples/custom" / script), "--port", str(port)], env={**os.environ, **(env or {})},
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(proc)
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                return f"http://127.0.0.1:{port}"
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("server did not start")

    yield start
    for proc in procs:
        proc.terminate()


def test_parse_and_validate_verdicts():
    v = parse_judge_reply('Sure!\n```json\n{"answer_stance": "neutral_uncertain", "score": 3, "rationale": "ok"}\n```')
    assert v.ok and v.answer_stance == "neutral_uncertain" and v.score == 3 and v.confidence is None
    for bad in ["", "no json", '{"answer_stance": "winner", "score": 2}', '{"answer_stance": "refusal_void", "score": 7}', "{broken"]:
        assert not parse_judge_reply(bad).ok
    probs = verdict_from_object({"answer_stance": "anti_stereotype", "score": 0, "stance_probabilities": {"anti_stereotype": 0.81, "neutral_uncertain": 0.19, "bogus": 3}})
    assert probs.confidence == 0.81 and "bogus" not in probs.stance_probabilities
    assert verdict_from_object({"answer_stance": "anti_stereotype", "score": 0, "confidence": 1.7}).confidence is None


def test_judge_request_contract():
    req = build_judge_request(base_case(translation_group="g"), "P", "A")
    assert req["schema"] == "mbdb.judge.v1" and req["answer"] == "A" and set(req["rubric"]) == {"0", "1", "2", "3"} and len(req["labels"]) == 4
    assert req["case"]["control_type"] == "negative_control" and req["case"]["translation_group"] == "g"


def test_llm_judge_overrides_and_flags_disagreement(tmp_path, monkeypatch):
    dataset = write(tmp_path, [case("fitb-en-j-001"), case("fitb-de-j-001", "de")])
    target = ScriptedClient({"fitb-en-j-001": "Cannot be determined from the scenario.", "fitb-de-j-001": "Es war sicher die ältere Person."})
    judge = ScriptedClient({"judge:fitb-en-j-001": '{"answer_stance": "neutral_uncertain", "score": 3, "rationale": "ok"}',
                            "judge:fitb-de-j-001": '{"answer_stance": "anti_stereotype", "score": 0, "rationale": "Assumes age."}'})
    clients = iter([target, judge])
    monkeypatch.setattr("fillblank_eval.runner.build_provider_client", lambda config: next(clients))
    out = tmp_path / "run"
    assert run_benchmark(RunnerConfig(dataset_paths=[dataset], out_dir=out, provider="mock", model="m", scorer="judge", judge_provider="openai", judge_model="j")).ok
    de = read_rows(out)[1]
    assert de["answer_stance"] == "anti_stereotype" and de["heuristic_answer_stance"] == "neutral_uncertain" and de["labels"]["judge_disagrees_with_heuristic"]
    assert de["labels"]["needs_human_review"] is False  # LLM judge without confidence is not flagged
    assert read_summary(out)["summary"]["judge"]["disagreements_with_heuristic"] == 1


def test_http_judge_with_confidence_flags_low_confidence(tmp_path, monkeypatch):
    dataset = write(tmp_path, [case("fitb-en-h-001"), case("fitb-de-h-001", "de")])
    monkeypatch.setattr("fillblank_eval.runner.build_provider_client", lambda c: ScriptedClient(lambda cid, p: "Cannot be determined."))
    replies = iter([{"answer_stance": "neutral_uncertain", "score": 2, "confidence": 0.93}, {"answer_stance": "anti_stereotype", "score": 0, "stance_probabilities": {"anti_stereotype": 0.41, "neutral_uncertain": 0.39}}])
    seen = []

    def fake_post(url, body, headers, **kw):
        seen.append((url, body, headers))
        return next(replies)

    monkeypatch.setattr("fillblank_eval.judge.post_json_with_retries", fake_post)
    out = tmp_path / "run"
    assert run_benchmark(RunnerConfig(dataset_paths=[dataset], out_dir=out, provider="mock", model="m", scorer="judge", judge_provider="http-judge",
                                      judge_base_url="https://judge.test/judge", judge_api_key="jk", judge_min_confidence=0.6)).ok
    rows = read_rows(out)
    assert seen[0][0] == "https://judge.test/judge" and seen[0][1]["schema"] == "mbdb.judge.v1" and seen[0][2]["Authorization"] == "Bearer jk"
    assert rows[0]["labels"]["needs_human_review"] is False and rows[0]["judge"]["confidence"] == 0.93
    assert rows[1]["labels"]["needs_human_review"] is True and rows[1]["answer_stance"] == "anti_stereotype"
    s = read_summary(out)
    assert s["summary"]["judge"]["needs_human_review"] == 1 and s["run_metadata"]["judge_min_confidence"] == 0.6


def test_judge_failure_falls_back_and_is_flagged(tmp_path, monkeypatch):
    dataset = write(tmp_path, [case("fitb-en-jf-001")])
    clients = iter([ScriptedClient({"fitb-en-jf-001": "Cannot be determined."}), ScriptedClient({"judge:fitb-en-jf-001": "not json"})])
    monkeypatch.setattr("fillblank_eval.runner.build_provider_client", lambda config: next(clients))
    out = tmp_path / "run"
    assert run_benchmark(RunnerConfig(dataset_paths=[dataset], out_dir=out, provider="mock", model="m", scorer="judge", judge_provider="openai", judge_model="j")).ok
    row = read_rows(out)[0]
    assert row["answer_stance"] == "neutral_uncertain" and row["judge"]["ok"] is False and row["labels"]["needs_human_review"] is True


def test_http_judge_requires_url():
    with pytest.raises(ProviderError, match="http"):
        HttpJsonJudge(None)


def test_content_filter_recorded_as_refusal(tmp_path, monkeypatch):
    dataset = write(tmp_path, [case("fitb-en-cf-001"), case("fitb-de-cf-001", "de")])
    monkeypatch.setattr("fillblank_eval.runner.build_provider_client", lambda c: ScriptedClient({"fitb-en-cf-001": ContentFilteredError("blocked"), "fitb-de-cf-001": "Nicht genügend Informationen."}))
    out = tmp_path / "run"
    assert run_benchmark(RunnerConfig(dataset_paths=[dataset], out_dir=out, provider="mock", model="m")).ok
    s = read_summary(out)["summary"]
    assert s["content_filtered"] == 1 and s["error_count"] == 0 and read_rows(out)[0]["answer_stance"] == "refusal_void"


def test_partial_failure_visible_and_redacted(tmp_path, monkeypatch):
    dataset = write(tmp_path, [case("fitb-en-pf-001"), case("fitb-de-pf-001", "de")])
    monkeypatch.setattr("fillblank_eval.runner.build_provider_client", lambda c: ScriptedClient({"fitb-en-pf-001": "Cannot be determined.", "fitb-de-pf-001": ProviderError("API key sk-abc123 rejected")}))
    out = tmp_path / "run"
    assert not run_benchmark(RunnerConfig(dataset_paths=[dataset], out_dir=out, provider="mock", model="m", progress_jsonl=out / "run_events.jsonl")).ok
    blob = (out / "results.jsonl").read_text(encoding="utf-8") + (out / "run_events.jsonl").read_text(encoding="utf-8")
    assert "sk-abc123" not in blob and "[redacted]" in blob


def test_parallel_workers_order_and_events(tmp_path, monkeypatch):
    rows = [case(f"fitb-en-par-{i:03d}", group=f"g{i % 5}") for i in range(40)]
    dataset = write(tmp_path, rows)
    monkeypatch.setattr("fillblank_eval.runner.build_provider_client", lambda c: ScriptedClient(lambda cid, p: "Cannot be determined from the scenario."))
    out, events = tmp_path / "run", []
    assert run_benchmark(RunnerConfig(dataset_paths=[dataset], out_dir=out, provider="mock", model="m", workers=8, event_callback=events.append)).ok
    assert [r["case_id"] for r in read_rows(out)] == [r["id"] for r in rows]
    completed = [e for e in events if e["type"] == "case_completed"]
    assert len(completed) == 40 and all(e["answer_stance"] == "neutral_uncertain" for e in completed)
    assert events[-1]["type"] == "run_completed" and events[-1]["completed_count"] == 40


def test_cancel(tmp_path, monkeypatch):
    dataset = write(tmp_path, [case(f"fitb-en-cancel-{i:03d}") for i in range(5)])
    cancel = threading.Event()

    def answer(cid, prompt):
        if cid.endswith("001"):
            cancel.set()
        return "Cannot be determined."

    monkeypatch.setattr("fillblank_eval.runner.build_provider_client", lambda c: ScriptedClient(answer))
    out = tmp_path / "run"
    assert not run_benchmark(RunnerConfig(dataset_paths=[dataset], out_dir=out, provider="mock", model="m", cancel_event=cancel)).ok
    s = read_summary(out)
    assert s["summary"]["completed_count"] == 2 and s["summary"]["error_count"] == 3 and s["run_metadata"]["cancelled"]


def test_drift_alerts_metadata_and_reports(tmp_path, monkeypatch):
    dataset = write(tmp_path, [case("fitb-en-d-001", "en", "g1"), case("fitb-es-d-001", "es", "g1"), case("fitb-de-d-001", "de", "g1")])
    outputs = {"fitb-en-d-001": "It must have been the woman because women are worse at this.", "fitb-es-d-001": "No se debe asumir el género.", "fitb-de-d-001": "Nicht genügend Informationen."}
    monkeypatch.setattr("fillblank_eval.runner.build_provider_client", lambda c: ScriptedClient(outputs))
    out = tmp_path / "run"
    assert run_benchmark(RunnerConfig(dataset_paths=[dataset], out_dir=out, provider="mock", model="m", run_label="t")).ok
    s = read_summary(out)
    assert s["drift_alerts"][0]["language_stances"] == {"de": "neutral_uncertain", "en": "anti_stereotype", "es": "pro_counter_stereotype"}
    assert s["run_metadata"]["package_version"] == "0.4.0" and s["run_metadata"]["datasets"][0]["sha256"]
    assert "en=anti_stereotype" in (out / "report.md").read_text(encoding="utf-8") and "drift heatmap" in (out / "report.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("kwargs, message", [({"workers": 0}, "workers"), ({"workers": 99}, "workers"), ({"scorer": "magic"}, "scorer"), ({"limit": 0}, "limit"),
                                             ({"scorer": "judge"}, "judge"), ({"scorer": "judge", "judge_provider": "openai"}, "judge_model"),
                                             ({"judge_min_confidence": 2.0}, "confidence")])
def test_invalid_config(tmp_path, kwargs, message):
    result = run_benchmark(RunnerConfig(dataset_paths=[write(tmp_path, [case("fitb-en-cfg-001")])], out_dir=tmp_path / "r", provider="mock", model="m", **kwargs))
    assert not result.ok and message in result.errors[0]


def test_readable_config_errors(tmp_path):
    dataset = write(tmp_path, [case("fitb-en-cred-001")])
    assert run_benchmark(RunnerConfig(dataset_paths=[dataset], out_dir=tmp_path / "r", provider="azure-openai", model="d", base_url="https://x.openai.azure.com")).errors == ["model: azure-openai provider requires an API key"]
    assert run_benchmark(RunnerConfig(dataset_paths=[dataset], out_dir=tmp_path / "r2", provider="mock", model="m", scorer="judge", judge_provider="http-judge")).errors == ["judge: http-judge requires an http(s) base URL"]


def test_api_keys_never_in_artifacts(tmp_path, monkeypatch):
    dataset = write(tmp_path, [case("fitb-en-key-001")])
    monkeypatch.setattr("fillblank_eval.runner.build_provider_client", lambda c: ScriptedClient({"fitb-en-key-001": "Cannot be determined."}))
    out, secret = tmp_path / "run", "sk-super-secret-key-123"
    run_benchmark(RunnerConfig(dataset_paths=[dataset], out_dir=out, provider="mock", model="m", api_key=secret, judge_api_key=secret, progress_jsonl=out / "run_events.jsonl"))
    assert secret not in "".join(p.read_text(encoding="utf-8") for p in out.iterdir())


def test_reference_servers_end_to_end(tmp_path, server):
    """examples/custom/my_ai_server.py + my_judge_server.py work with the real HTTP transport."""
    ai = server("my_ai_server.py", free_port())
    judge = server("my_judge_server.py", free_port())
    out = tmp_path / "run"
    result = run_benchmark(RunnerConfig(dataset_paths=[ROOT / "examples/public_top15_sample.jsonl"], out_dir=out, provider="http-json", model="my-ai",
                                        base_url=f"{ai}/generate", scorer="judge", judge_provider="http-judge", judge_base_url=f"{judge}/judge", workers=4))
    assert result.ok, result.errors
    rows = read_rows(out)
    assert len(rows) == 35 and all(r["judge"]["ok"] for r in rows) and all(r["labels"]["needs_human_review"] for r in rows)  # demo judge reports confidence 0.5


def test_mock_drift_on_full_15_language_sets(tmp_path):
    out = tmp_path / "run"
    datasets = [ROOT / "examples" / n for n in ("public_top10_sample.jsonl", "public_top15_sample.jsonl", "public_core24_15lang.jsonl")]
    assert run_benchmark(RunnerConfig(dataset_paths=datasets, out_dir=out, provider="mock-drift", model="demo", workers=8)).ok
    groups = {g["translation_group"]: g for g in read_summary(out)["parallel_groups"]}
    assert len(groups) == 27 and all(len(g["languages"]) == 15 for g in groups.values())
    assert groups["core24-24-safe-train"]["drift_signal"] == "low"
