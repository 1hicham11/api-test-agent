"""Final report models: per-case verdicts, anomalies, and the full report."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low"]

SEVERITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}

AnomalyType = Literal[
    "server_error",
    "schema_mismatch",
    "undocumented_status",
    "slow_response",
]


class Anomaly(BaseModel):
    """A single detected deviation between the API's behavior and its spec."""

    severity: Severity
    type: AnomalyType
    endpoint: str = Field(description="'METHOD /path' the anomaly was observed on")
    case_name: str | None = None
    detail: str


class CaseResult(BaseModel):
    """Pass/fail verdict for one executed test case."""

    case_id: str
    name: str
    category: str
    endpoint: str
    expected_status: int
    actual_status: int | None
    latency_ms: float
    passed: bool
    failure_reason: str | None = None


class Report(BaseModel):
    """The complete analysis report, stored as JSON and rendered as HTML."""

    report_id: str
    created_at: str
    status: Literal["completed", "failed"]
    target_url: str
    spec_title: str | None = None
    total_endpoints: int = 0
    tested_endpoints: int = 0
    coverage_percent: float = 0.0
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    results: list[CaseResult] = Field(default_factory=list)
    anomalies: list[Anomaly] = Field(default_factory=list)
    pytest_dir: str | None = None
    notes: list[str] = Field(default_factory=list)
    error: str | None = None
    error_explanation: str | None = None

    def sorted_anomalies(self) -> list[Anomaly]:
        """Anomalies ranked most-severe first."""
        return sorted(self.anomalies, key=lambda a: SEVERITY_ORDER.get(a.severity, 9))
