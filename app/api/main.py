"""Agent HTTP API.

Endpoints:
    GET  /                   — product landing page
    GET  /dashboard          — launch analyses, browse past runs
    POST /analyze            — start an analysis (spec file/URL + target URL)
    GET  /reports            — list past runs
    GET  /reports/{id}       — report as JSON
    GET  /reports/{id}/html  — report as a readable HTML page
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse

from app.api import storage
from app.api.home import render_dashboard, render_landing
from app.api.html_report import render_html, render_pending
from app.config import settings
from app.graph.workflow import run_workflow
from app.models.report import Report
from app.models.state import AgentState

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    storage.init_db()
    yield


app = FastAPI(
    title="API Test Agent",
    description=(
        "AI agent that reads an OpenAPI spec, generates realistic test "
        "scenarios with an LLM, executes them against a running API, and "
        "reports coverage and anomalies."
    ),
    version="0.1.0",
    lifespan=_lifespan,
)

# Bundle the deliberately-buggy demo API in-process so a single deployed service
# is self-contained: its spec lives at /demo/openapi.json and its base URL is
# /demo. Disable with MOUNT_DEMO=0 (e.g. when running the demo as its own server).
if settings.mount_demo:
    from app.demo_api.main import app as demo_app

    app.mount("/demo", demo_app)


def _ensure_target_allowed(request: Request, url: str, field: str) -> None:
    """Guard against the public demo being used as an open proxy.

    When AGENT_RESTRICT_TARGETS is on, /analyze may only reach the app's own
    host (the bundled /demo API) or explicitly allowlisted hosts — otherwise
    anyone could point it at an arbitrary address or burn the Groq quota.
    Off by default, so local use stays unrestricted.
    """
    if not settings.restrict_targets:
        return
    host = (urlparse(url).hostname or "").lower()
    allowed = {
        (request.url.hostname or "").lower(),
        "127.0.0.1",
        "localhost",
        *settings.allowed_target_hosts,
    }
    if host not in allowed:
        raise HTTPException(
            403,
            f"{field} host {host!r} is not allowed on this public demo; "
            "it only analyzes the bundled demo API at /demo.",
        )


def _run_analysis(state: AgentState) -> None:
    """Background task: run the LangGraph workflow and persist the result."""
    try:
        final = run_workflow(state)
        report = final.report
        if report is None:  # defensive: both terminal nodes set a report
            raise RuntimeError("workflow finished without producing a report")
        storage.save_report(state.report_id, report)
    except Exception as exc:  # noqa: BLE001 - persist any crash for the client
        logger.exception("Analysis %s crashed", state.report_id)
        storage.mark_crashed(state.report_id, str(exc))


@app.get("/", response_class=HTMLResponse)
def landing() -> HTMLResponse:
    """Product landing page."""
    return HTMLResponse(render_landing())


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    """Dashboard: analysis launcher + list of past runs."""
    return HTMLResponse(render_dashboard(storage.list_reports()))


@app.post("/analyze", status_code=202)
def analyze(
    request: Request,
    background_tasks: BackgroundTasks,
    target_url: str = Form(..., description="Base URL of the running API under test"),
    spec_url: str | None = Form(None, description="URL of the OpenAPI spec"),
    spec_file: UploadFile | None = File(None, description="OpenAPI spec file (JSON/YAML)"),
    auth_headers: str | None = Form(
        None,
        description='Optional JSON object of headers, e.g. {"Authorization": "Bearer ..."}',
    ),
) -> dict[str, str]:
    """Start an analysis run; returns a report id to poll."""
    # Browsers submit an empty file part when the input is left blank —
    # only treat the upload as a spec if it has a filename and content.
    spec_url = (spec_url or "").strip() or None
    raw_spec: str | None = None
    if spec_file is not None and (spec_file.filename or "").strip():
        content = spec_file.file.read().decode("utf-8", errors="replace")
        raw_spec = content if content.strip() else None
    if not spec_url and raw_spec is None:
        raise HTTPException(422, "provide either spec_url or spec_file")

    # Both target_url and spec_url are fetched server-side, so both are checked.
    _ensure_target_allowed(request, target_url, "target_url")
    if spec_url:
        _ensure_target_allowed(request, spec_url, "spec_url")

    parsed_headers: dict[str, str] = {}
    if auth_headers:
        try:
            loaded = json.loads(auth_headers)
            if not isinstance(loaded, dict):
                raise ValueError("must be a JSON object")
            parsed_headers = {str(k): str(v) for k, v in loaded.items()}
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(422, f"auth_headers must be a JSON object: {exc}") from exc

    report_id = uuid.uuid4().hex[:12]
    storage.create_report(report_id, target_url)
    state = AgentState(
        report_id=report_id,
        target_base_url=target_url,
        raw_spec=raw_spec,
        spec_url=spec_url,
        auth_headers=parsed_headers,
    )
    background_tasks.add_task(_run_analysis, state)
    return {
        "report_id": report_id,
        "status": "running",
        "report_url": f"/reports/{report_id}",
        "html_url": f"/reports/{report_id}/html",
    }


@app.get("/reports")
def list_reports() -> list[dict[str, Any]]:
    """Summaries of all analysis runs, newest first."""
    return storage.list_reports()


@app.get("/reports/{report_id}")
def get_report(report_id: str) -> dict[str, Any]:
    """Full report as JSON (``report`` is null while the run is in progress)."""
    row = storage.get_report(report_id)
    if row is None:
        raise HTTPException(404, f"no report with id {report_id}")
    return row


@app.get("/reports/{report_id}/html", response_class=HTMLResponse)
def get_report_html(report_id: str) -> HTMLResponse:
    """Readable HTML version of the report."""
    row = storage.get_report(report_id)
    if row is None:
        raise HTTPException(404, f"no report with id {report_id}")
    if row["report"] is None:
        detail = row["error"] or "the agent is parsing, planning, generating and executing tests"
        return HTMLResponse(render_pending(report_id, row["status"], detail))
    return HTMLResponse(render_html(Report.model_validate(row["report"])))


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
