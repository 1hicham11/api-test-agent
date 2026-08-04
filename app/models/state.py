"""The shared LangGraph state, passed through every node."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.plan import EndpointTestPlan
from app.models.report import Anomaly, CaseResult, Report
from app.models.spec import ParsedSpec
from app.models.testcase import ExecutionResult, TestCase


class AgentState(BaseModel):
    """Typed state schema for the StateGraph.

    Nodes read the fields they need and return partial updates as dicts;
    LangGraph merges them back into this model.
    """

    # --- inputs ---
    report_id: str
    target_base_url: str
    raw_spec: str | None = Field(
        default=None, description="Raw spec text (JSON or YAML), if uploaded directly"
    )
    spec_url: str | None = Field(default=None, description="URL to fetch the spec from")
    auth_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Headers (e.g. Authorization) merged into every non-negative-auth request",
    )

    # --- spec parsing ---
    parsed_spec: ParsedSpec | None = None
    spec_error: str | None = None

    # --- planning & generation (LLM) ---
    test_plans: list[EndpointTestPlan] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)

    # --- execution ---
    execution_results: list[ExecutionResult] = Field(default_factory=list)
    pytest_dir: str | None = None

    # --- validation ---
    case_results: list[CaseResult] = Field(default_factory=list)
    anomalies: list[Anomaly] = Field(default_factory=list)

    # --- output ---
    notes: list[str] = Field(default_factory=list)
    error_explanation: str | None = None
    report: Report | None = None
