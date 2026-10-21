"""FastAPI web app for the Multilingual Bias Drift Benchmark.

Start locally:   fillblank-web --open      (or: start.ps1 on Windows)
Container:       docker compose up --build
"""
from __future__ import annotations

import hmac
import json
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from fillblank_eval import __version__
from fillblank_eval.provider_client import PROVIDERS, normalize_provider
from fillblank_eval.runner import MOCK_PROVIDERS
from fillblank_eval.scorer import SCORER_VERSION
from fillblank_eval.validator import LANGUAGE_NAMES, PUBLIC_CAVEAT

from .runs import TERMINAL, RunManager
from .settings import Settings

STATIC_DIR = Path(__file__).parent / "static"
ARTIFACTS = {"summary.json": "application/json", "results.jsonl": "application/x-ndjson", "report.md": "text/markdown; charset=utf-8",
             "report.html": "text/html; charset=utf-8", "run_events.jsonl": "application/x-ndjson"}
UI_CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'; base-uri 'none'"


class EndpointSpec(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(default="", max_length=200)
    profile: str | None = Field(default=None, max_length=40)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=4000)
    api_version: str | None = Field(default=None, max_length=40)


class RunRequest(EndpointSpec):
    datasets: list[str] = Field(min_length=1, max_length=20)
    limit: int | None = Field(default=None, ge=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=256, ge=16, le=4096)
    workers: int = Field(default=1, ge=1, le=16)
    scorer: Literal["heuristic", "judge"] = "heuristic"
    judge: EndpointSpec | None = None
    label: str | None = Field(default=None, max_length=120)

    @field_validator("datasets")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class UploadRequest(BaseModel):
    filename: str = Field(default="dataset.jsonl", max_length=200)
    content: str = Field(min_length=2)


def _is_local_host(hostname: str) -> bool:
    if hostname in {"localhost", "host.docker.internal"} or hostname.endswith(".local"):
        return True
    try:
        address = ip_address(hostname)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    manager = RunManager(settings)
    app = FastAPI(title="Multilingual Bias Drift Benchmark", version=__version__, docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
    app.state.settings = settings
    app.state.manager = manager

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        if request.url.path.startswith("/api/docs"):
            return response
        response.headers.setdefault("Content-Security-Policy", UI_CSP)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def require_token(request: Request) -> None:
        if not settings.app_token:
            return
        supplied = request.headers.get("x-api-token") or ""
        auth_header = request.headers.get("authorization") or ""
        if auth_header.lower().startswith("bearer "):
            supplied = supplied or auth_header[7:]
        if not hmac.compare_digest(supplied.encode(), settings.app_token.encode()):
            raise HTTPException(status_code=401, detail="missing or invalid API token")

    auth = [Depends(require_token)]

    def resolve_endpoint(spec: EndpointSpec, *, role: str) -> dict[str, Any]:
        provider = normalize_provider(spec.provider)
        if provider not in PROVIDERS:
            raise HTTPException(422, f"{role}: unsupported provider {spec.provider!r}")
        if provider not in settings.enabled_providers:
            raise HTTPException(422, f"{role}: provider {provider!r} is disabled on this server")
        if spec.profile:
            profile = settings.profiles.get(spec.profile)
            if profile is None or profile.provider != provider:
                raise HTTPException(422, f"{role}: unknown server profile {spec.profile!r} for provider {provider!r}")
            model = spec.model or (profile.models[0] if profile.models else "")
            if not model:
                raise HTTPException(422, f"{role}: a model/deployment name is required")
            if profile.models and model not in profile.models and not settings.allow_custom_endpoints:
                raise HTTPException(422, f"{role}: model {model!r} is not offered by profile {profile.name!r}")
            return {"provider": provider, "model": model, "base_url": profile.base_url, "api_key": profile.api_key, "api_version": spec.api_version or profile.api_version}
        if provider in MOCK_PROVIDERS:
            return {"provider": provider, "model": spec.model or "mock-model", "base_url": None, "api_key": None, "api_version": None}
        if not spec.model:
            raise HTTPException(422, f"{role}: a model/deployment name is required")
        if spec.api_key and not settings.allow_user_keys:
            raise HTTPException(422, f"{role}: user-supplied API keys are disabled; use a server profile")
        if PROVIDERS[provider].get("needs_key") and not spec.api_key:
            raise HTTPException(422, f"{role}: an API key is required for {provider} (or choose a server profile)")
        if spec.base_url:
            if not settings.allow_custom_endpoints:
                raise HTTPException(422, f"{role}: custom endpoints are disabled on this server; use a server profile")
            parsed = urlparse(spec.base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise HTTPException(422, f"{role}: base_url must be an http(s) URL")
            if parsed.scheme == "http" and not _is_local_host(parsed.hostname) and provider != "ollama":
                raise HTTPException(422, f"{role}: plain http is only allowed for local endpoints; use https")
        elif PROVIDERS[provider].get("needs_base_url"):
            raise HTTPException(422, f"{role}: base_url is required for {provider}")
        return {"provider": provider, "model": spec.model, "base_url": spec.base_url, "api_key": spec.api_key, "api_version": spec.api_version}

    def public_endpoint_view(spec: EndpointSpec | None, resolved: dict[str, Any] | None) -> dict[str, Any] | None:
        if spec is None or resolved is None:
            return None
        return {"provider": resolved["provider"], "model": resolved["model"], "profile": spec.profile,
                "base_url": resolved["base_url"] if not spec.profile else None, "api_version": resolved["api_version"], "api_key_supplied": bool(spec.api_key)}

    def run_or_404(run_id: str):
        state = manager.get(run_id)
        if state is None:
            raise HTTPException(404, "run not found")
        return state

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/meta", dependencies=auth)
    def meta() -> dict[str, Any]:
        return {
            "version": __version__, "scorer_version": SCORER_VERSION, "caveat": PUBLIC_CAVEAT,
            "providers": {name: PROVIDERS[name] for name in settings.enabled_providers},
            "profiles": [p.public_view() for p in settings.profiles.values() if p.provider in settings.enabled_providers],
            "languages": LANGUAGE_NAMES,
            "limits": {"max_cases_per_run": settings.max_cases_per_run, "max_workers": settings.max_workers, "max_concurrent_runs": settings.max_concurrent_runs,
                       "allow_user_keys": settings.allow_user_keys, "allow_custom_endpoints": settings.allow_custom_endpoints},
            "auth_required": bool(settings.app_token),
        }

    @app.get("/api/datasets", dependencies=auth)
    def datasets() -> dict[str, Any]:
        return {"builtin": manager.builtin_datasets(), "uploads": manager.uploaded_datasets()}

    @app.post("/api/datasets", dependencies=auth)
    def upload_dataset(body: UploadRequest) -> JSONResponse:
        try:
            result = manager.save_upload(body.filename, body.content)
        except ValueError as exc:
            raise HTTPException(413, str(exc)) from exc
        return JSONResponse(result, status_code=201 if result.get("ok") else 422)

    @app.delete("/api/datasets/{upload_id}", dependencies=auth)
    def delete_dataset(upload_id: str) -> dict[str, Any]:
        if not manager.delete_upload(upload_id):
            raise HTTPException(404, "dataset not found")
        return {"deleted": upload_id}

    @app.get("/api/runs", dependencies=auth)
    def list_runs() -> dict[str, Any]:
        return {"runs": manager.list_runs()}

    @app.post("/api/runs", dependencies=auth, status_code=202)
    def create_run(body: RunRequest) -> dict[str, Any]:
        target = resolve_endpoint(body, role="model")
        judge = None
        if body.scorer == "judge":
            if body.judge is None:
                raise HTTPException(422, "scorer=judge requires a judge endpoint")
            judge = resolve_endpoint(body.judge, role="judge")
        try:
            dataset_paths = [manager.resolve_dataset(dataset_id) for dataset_id in body.datasets]
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        limit = min(body.limit or settings.max_cases_per_run, settings.max_cases_per_run)
        config_kwargs = {
            "dataset_paths": dataset_paths, "provider": target["provider"], "model": target["model"], "base_url": target["base_url"],
            "api_key": target["api_key"], "api_version": target["api_version"], "temperature": body.temperature, "max_tokens": body.max_tokens,
            "limit": limit, "workers": min(body.workers, settings.max_workers), "scorer": body.scorer,
            "judge_provider": judge["provider"] if judge else None, "judge_model": judge["model"] if judge else None,
            "judge_base_url": judge["base_url"] if judge else None, "judge_api_key": judge["api_key"] if judge else None,
            "judge_api_version": judge["api_version"] if judge else None, "run_label": body.label,
        }
        public_request = {"target": public_endpoint_view(body, target), "judge": public_endpoint_view(body.judge, judge), "datasets": body.datasets,
                          "limit": limit, "temperature": body.temperature, "max_tokens": body.max_tokens, "workers": config_kwargs["workers"],
                          "scorer": body.scorer, "label": body.label}
        return manager.start(config_kwargs, public_request).public_view()

    @app.get("/api/runs/{run_id}", dependencies=auth)
    def get_run(run_id: str) -> dict[str, Any]:
        state = run_or_404(run_id)
        view = state.public_view()
        summary_path = state.out_dir / "summary.json"
        if state.status in TERMINAL and summary_path.is_file():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            view["summary"] = {key: summary.get(key) for key in ("summary", "breakdowns", "parallel_groups", "drift_alerts", "run_metadata", "interpretation", "caveat", "errors")}
        return view

    @app.get("/api/runs/{run_id}/live", dependencies=auth)
    def get_live(run_id: str) -> dict[str, Any]:
        return manager.live_view(run_or_404(run_id))

    @app.get("/api/runs/{run_id}/results", dependencies=auth)
    def get_results(run_id: str) -> dict[str, Any]:
        state = run_or_404(run_id)
        path = state.out_dir / "results.jsonl"
        if not path.is_file():
            raise HTTPException(404, "results not available yet")
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                row.pop("raw_response", None)
                rows.append(row)
        return {"rows": rows}

    @app.get("/api/runs/{run_id}/artifacts/{name}", dependencies=auth)
    def get_artifact(run_id: str, name: str) -> Response:
        state = run_or_404(run_id)
        if name not in ARTIFACTS:
            raise HTTPException(404, "unknown artifact")
        path = state.out_dir / name
        if not path.is_file():
            raise HTTPException(404, "artifact not available")
        response = FileResponse(path, media_type=ARTIFACTS[name], filename=f"{run_id}-{name}" if name != "report.html" else None)
        if name == "report.html":
            response.headers["Content-Security-Policy"] = REPORT_CSP
        return response

    @app.post("/api/runs/{run_id}/cancel", dependencies=auth)
    def cancel_run(run_id: str) -> dict[str, Any]:
        run_or_404(run_id)
        if not manager.cancel(run_id):
            raise HTTPException(409, "run is not active")
        return {"cancelled": run_id}

    @app.delete("/api/runs/{run_id}", dependencies=auth)
    def delete_run(run_id: str) -> dict[str, Any]:
        run_or_404(run_id)
        try:
            manager.delete(run_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"deleted": run_id}

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html; charset=utf-8")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
