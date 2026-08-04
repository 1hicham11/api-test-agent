"""Report node: aggregate everything into the final :class:`Report`."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.models.report import SEVERITY_ORDER, Report
from app.models.state import AgentState

logger = logging.getLogger(__name__)


def build_report_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: compute coverage and assemble the final report."""
    spec = state.parsed_spec
    total_endpoints = len(spec.endpoints) if spec else 0
    tested = {r.endpoint for r in state.case_results}
    tested_endpoints = len(
        {e.key for e in spec.endpoints if e.key in tested} if spec else set()
    )
    coverage = (100.0 * tested_endpoints / total_endpoints) if total_endpoints else 0.0
    passed = sum(1 for r in state.case_results if r.passed)

    report = Report(
        report_id=state.report_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        status="completed",
        target_url=state.target_base_url,
        spec_title=spec.title if spec else None,
        total_endpoints=total_endpoints,
        tested_endpoints=tested_endpoints,
        coverage_percent=round(coverage, 1),
        total_cases=len(state.case_results),
        passed_cases=passed,
        failed_cases=len(state.case_results) - passed,
        results=state.case_results,
        anomalies=sorted(
            state.anomalies, key=lambda a: SEVERITY_ORDER.get(a.severity, 9)
        ),
        pytest_dir=state.pytest_dir,
        notes=state.notes,
    )
    logger.info(
        "Report %s: %.1f%% coverage, %d/%d passed, %d anomalies",
        report.report_id,
        report.coverage_percent,
        report.passed_cases,
        report.total_cases,
        len(report.anomalies),
    )
    return {"report": report}
