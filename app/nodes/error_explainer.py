"""Error-explanation node: reached via the conditional edge when spec
parsing fails, instead of continuing the pipeline.

Uses the LLM to explain the problem in plain language when available, with a
deterministic fallback so the node never fails.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.llm import get_llm
from app.models.report import Report
from app.models.state import AgentState

logger = logging.getLogger(__name__)

_FALLBACK = (
    "The OpenAPI spec could not be processed. Check that the document is valid "
    "JSON or YAML, declares 'openapi: 3.x', and defines at least one operation "
    "under 'paths'. Original error: {error}"
)


def _llm_explanation(error: str) -> str | None:
    """Ask the LLM for a short, actionable explanation; None on any failure."""
    try:
        llm = get_llm(temperature=0.0)
        response = llm.invoke(
            "An OpenAPI spec failed validation with this error:\n"
            f"{error[:1500]}\n\n"
            "In 3 sentences or fewer, explain in plain language what is wrong "
            "and how to fix it. No preamble."
        )
        text = str(response.content).strip()
        return text or None
    except Exception:  # noqa: BLE001 - explanation is best-effort
        logger.warning("LLM explanation unavailable, using fallback text")
        return None


def explain_error_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: produce a failed report with a readable explanation."""
    error = state.spec_error or "unknown spec error"
    explanation = _llm_explanation(error) or _FALLBACK.format(error=error)

    report = Report(
        report_id=state.report_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        status="failed",
        target_url=state.target_base_url,
        notes=state.notes,
        error=error,
        error_explanation=explanation,
    )
    return {"error_explanation": explanation, "report": report}
