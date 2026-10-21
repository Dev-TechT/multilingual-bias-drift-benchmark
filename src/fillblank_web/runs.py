"""Background run management for the web app.

- Runs execute in worker threads, limited by a semaphore (MBDB_MAX_CONCURRENT_RUNS).
- API keys are passed to the runner in memory only. They are never written to disk,
  never stored in run metadata and never returned by the API.
- Each run writes the normal runner artifacts to ``<data_dir>/runs/<run_id>/`` plus a
  sanitized ``meta.json`` (and ``plan.json`` for the live view) so history survives restarts.
- The live view (``live_view``) exposes the planned question x language grid and every
  answer stance as soon as it arrives.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fillblank_eval.runner import RunnerConfig, load_public_cases, run_benchmark
from fillblank_eval.validator import validate_dataset

from .settings import Settings

RUN_ID_RE = re.compile(r"^[a-f0-9]{12}$")
UPLOAD_ID_RE = re.compile(r"^upload-[a-f0-9]{12}$")
BUILTIN_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_plan(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Question x language grid for the live view. Cases without translation_group form their own row."""
    groups: dict[str, dict[str, Any]] = {}
    languages: list[str] = []
    for case in cases:
        group_id = case.get("translation_group") or case["id"]
        group = groups.setdefault(group_id, {"id": group_id, "label": None, "control_type": case.get("control_type"), "construct": case.get("construct"), "cells": {}})
        language = case.get("language") or "?"
        group["cells"][language] = case["id"]
        if language == "en" or group["label"] is None:
            group["label"] = str(case.get("prompt_template", ""))[:160]
        if language not in languages:
            languages.append(language)
    preferred = ["en", "de", "zh", "hi", "es", "ar", "fr", "bn", "pt", "ru", "id", "ur", "ja", "vi", "tr", "el"]
    languages.sort(key=lambda lang: (preferred.index(lang) if lang in preferred else len(preferred), lang))
    return {"languages": languages, "groups": list(groups.values()), "total": len(cases)}


@dataclass
class RunState:
    run_id: str
    status: str
    created_at: str
    request: dict[str, Any]
    out_dir: Path
    total: int = 0
    completed: int = 0
    errors: int = 0
    last_event: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    ok: bool | None = None
    plan: dict[str, Any] | None = None
    live: dict[str, dict[str, Any]] = field(default_factory=dict)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def public_view(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "request": self.request,
            "progress": {"total": self.total, "completed": self.completed, "errors": self.errors, "last_case": self.last_event.get("case_id")},
            "ok": self.ok,
            "messages": self.messages[-20:],
            "has_artifacts": (self.out_dir / "summary.json").is_file(),
        }


class RunManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.runs_dir = settings.data_dir / "runs"
        self.uploads_dir = settings.data_dir / "datasets"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self._runs: dict[str, RunState] = {}
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(settings.max_concurrent_runs)
        self._load_history()

    # -- datasets --------------------------------------------------------------
    def builtin_datasets(self) -> list[dict[str, Any]]:
        items = []
        for path in sorted(self.settings.datasets_dir.glob("*.jsonl")):
            result = validate_dataset(path, public_mode=True)
            items.append({"id": path.stem, "kind": "builtin", "case_count": result.case_count, "languages": result.languages or [], "ok": result.ok})
        return items

    def uploaded_datasets(self) -> list[dict[str, Any]]:
        items = []
        for meta_path in sorted(self.uploads_dir.glob("upload-*.json")):
            try:
                items.append(json.loads(meta_path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return items

    def resolve_dataset(self, dataset_id: str) -> Path:
        if UPLOAD_ID_RE.match(dataset_id):
            path = self.uploads_dir / f"{dataset_id}.jsonl"
        elif BUILTIN_RE.match(dataset_id):
            path = self.settings.datasets_dir / f"{dataset_id}.jsonl"
        else:
            raise ValueError(f"invalid dataset id: {dataset_id!r}")
        if not path.is_file():
            raise ValueError(f"unknown dataset: {dataset_id!r}")
        return path

    def save_upload(self, filename: str, content: str) -> dict[str, Any]:
        if len(content.encode("utf-8")) > self.settings.max_upload_bytes:
            raise ValueError(f"dataset is larger than {self.settings.max_upload_bytes} bytes")
        upload_id = f"upload-{uuid.uuid4().hex[:12]}"
        path = self.uploads_dir / f"{upload_id}.jsonl"
        path.write_text(content, encoding="utf-8")
        result = validate_dataset(path, public_mode=True)
        if not result.ok:
            path.unlink(missing_ok=True)
            return {"ok": False, "errors": result.errors[:50], "case_count": result.case_count}
        meta = {"id": upload_id, "kind": "upload", "filename": re.sub(r"[^A-Za-z0-9_. -]+", "_", filename)[:120] or "dataset.jsonl",
                "case_count": result.case_count, "languages": result.languages or [], "ok": True, "uploaded_at": _now()}
        (self.uploads_dir / f"{upload_id}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return {**meta, "errors": []}

    def delete_upload(self, upload_id: str) -> bool:
        if not UPLOAD_ID_RE.match(upload_id):
            return False
        found = False
        for suffix in (".jsonl", ".json"):
            path = self.uploads_dir / f"{upload_id}{suffix}"
            if path.exists():
                path.unlink()
                found = True
        return found

    # -- runs ------------------------------------------------------------------
    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            runs = list(self._runs.values())
        return [run.public_view() for run in sorted(runs, key=lambda run: run.created_at, reverse=True)]

    def get(self, run_id: str) -> RunState | None:
        if not RUN_ID_RE.match(run_id or ""):
            return None
        with self._lock:
            return self._runs.get(run_id)

    def start(self, config_kwargs: dict[str, Any], public_request: dict[str, Any]) -> RunState:
        run_id = uuid.uuid4().hex[:12]
        out_dir = self.runs_dir / run_id
        out_dir.mkdir(parents=True, exist_ok=False)
        cases, _ = load_public_cases(list(config_kwargs["dataset_paths"]), config_kwargs.get("limit"))
        plan = build_plan(cases)
        state = RunState(run_id=run_id, status="queued", created_at=_now(), request=public_request, out_dir=out_dir, plan=plan, total=plan["total"])
        (out_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        with self._lock:
            self._runs[run_id] = state
        self._write_meta(state)
        threading.Thread(target=self._execute, args=(state, config_kwargs), name=f"run-{run_id}", daemon=True).start()
        return state

    def cancel(self, run_id: str) -> bool:
        state = self.get(run_id)
        if state is None or state.status in TERMINAL:
            return False
        state.cancel_event.set()
        state.messages.append("cancellation requested")
        return True

    def delete(self, run_id: str) -> bool:
        state = self.get(run_id)
        if state is None:
            return False
        if state.status not in TERMINAL:
            raise ValueError("run is still active; cancel it first")
        with self._lock:
            self._runs.pop(run_id, None)
        shutil.rmtree(state.out_dir, ignore_errors=True)
        return True

    def live_view(self, state: RunState) -> dict[str, Any]:
        plan = state.plan
        if plan is None and (state.out_dir / "plan.json").is_file():
            plan = json.loads((state.out_dir / "plan.json").read_text(encoding="utf-8"))
        answers = dict(state.live)
        results_path = state.out_dir / "results.jsonl"
        if not answers and results_path.is_file():  # history after restart
            rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            answers = {row["case_id"]: {"stance": row.get("answer_stance"), "score": row.get("score"), "error": bool(row.get("error"))} for row in rows}
            if plan is None:
                plan = build_plan([{"id": r["case_id"], "language": r.get("language"), "translation_group": r.get("translation_group"),
                                    "control_type": r.get("control_type"), "construct": r.get("construct"), "prompt_template": ""} for r in rows])
        return {"run_id": state.run_id, "status": state.status, "progress": state.public_view()["progress"],
                "plan": plan or {"languages": [], "groups": [], "total": 0}, "answers": answers}

    def _on_event(self, state: RunState, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "run_started":
            state.total = int(event.get("case_count") or 0)
        elif event_type in {"case_completed", "case_failed"}:
            # With parallel workers, events can arrive out of order: counters only grow.
            state.completed = max(state.completed, int(event.get("completed_count") or 0))
            state.errors = max(state.errors, int(event.get("error_count") or 0))
            state.last_event = {"case_id": event.get("case_id"), "type": event_type}
            state.live[str(event.get("case_id"))] = {"stance": event.get("answer_stance") or "refusal_void", "score": event.get("score"), "error": event_type == "case_failed"}
        elif event_type == "run_completed":
            state.completed = int(event.get("completed_count") or 0)
            state.errors = int(event.get("error_count") or 0)

    def _execute(self, state: RunState, config_kwargs: dict[str, Any]) -> None:
        with self._slots:
            if state.cancel_event.is_set():
                state.status, state.finished_at = "cancelled", _now()
                self._write_meta(state)
                return
            state.status, state.started_at = "running", _now()
            self._write_meta(state)
            try:
                config = RunnerConfig(**config_kwargs, out_dir=state.out_dir, progress_jsonl=state.out_dir / "run_events.jsonl",
                                      event_callback=lambda event: self._on_event(state, event), cancel_event=state.cancel_event)
                result = run_benchmark(config)
                state.ok = result.ok
                state.messages.extend(result.errors[:50])
                if state.cancel_event.is_set():
                    state.status = "cancelled"
                elif (state.out_dir / "summary.json").is_file():
                    state.status = "completed"  # may contain per-case errors; see ok/messages
                else:
                    state.status = "failed"
            except Exception as exc:  # noqa: BLE001 - surface a safe message only
                state.ok = False
                state.status = "failed"
                state.messages.append(f"internal error: {type(exc).__name__}")
            finally:
                state.finished_at = _now()
                self._write_meta(state)

    def _write_meta(self, state: RunState) -> None:
        (state.out_dir / "meta.json").write_text(json.dumps(state.public_view(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_history(self) -> None:
        for meta_path in self.runs_dir.glob("*/meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            run_id = meta.get("run_id")
            if not isinstance(run_id, str) or not RUN_ID_RE.match(run_id):
                continue
            status = meta.get("status", "interrupted")
            if status not in TERMINAL:
                status = "interrupted"
            progress = meta.get("progress") or {}
            self._runs[run_id] = RunState(run_id=run_id, status=status, created_at=meta.get("created_at") or _now(), request=meta.get("request") or {},
                                          out_dir=meta_path.parent, total=int(progress.get("total") or 0), completed=int(progress.get("completed") or 0),
                                          errors=int(progress.get("errors") or 0), messages=list(meta.get("messages") or []),
                                          started_at=meta.get("started_at"), finished_at=meta.get("finished_at"), ok=meta.get("ok"))
