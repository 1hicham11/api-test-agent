"""Validation & anomaly node: compare actual responses against the spec.

Flags: undocumented status codes, response-schema mismatches, 5xx errors,
and suspiciously slow endpoints. Pure Python — no LLM.
"""

from __future__ import annotations

import logging
from typing import Any

import jsonschema

from app.config import settings
from app.models.report import Anomaly, CaseResult
from app.models.spec import EndpointInfo
from app.models.state import AgentState
from app.models.testcase import ExecutionResult

logger = logging.getLogger(__name__)


def openapi_to_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert OpenAPI schema quirks to plain JSON Schema for validation.

    Handles ``nullable: true`` (OpenAPI 3.0) and the boolean form of
    ``exclusiveMinimum``/``exclusiveMaximum``. Unknown keywords are left in
    place — jsonschema ignores them.
    """
    if not isinstance(schema, dict):
        return schema
    converted: dict[str, Any] = {}
    for key, value in schema.items():
        if isinstance(value, dict):
            converted[key] = openapi_to_json_schema(value)
        elif isinstance(value, list):
            converted[key] = [
                openapi_to_json_schema(v) if isinstance(v, dict) else v for v in value
            ]
        else:
            converted[key] = value
    if converted.pop("nullable", False):
        current_type = converted.get("type")
        if isinstance(current_type, str):
            converted["type"] = [current_type, "null"]
    for bound, limit in (("exclusiveMinimum", "minimum"), ("exclusiveMaximum", "maximum")):
        if isinstance(converted.get(bound), bool):
            if converted[bound] and limit in converted:
                converted[bound] = converted.pop(limit)
            else:
                converted.pop(bound)
    return converted


def find_declared_schema(
    endpoint: EndpointInfo, status_code: int
) -> tuple[bool, dict[str, Any] | None]:
    """Return (is_documented, body_schema) for a status on an endpoint.

    Supports exact codes, OpenAPI range keys like ``4XX``, and ``default``.
    """
    exact = str(status_code)
    if exact in endpoint.responses:
        return True, endpoint.responses[exact]
    range_key = f"{status_code // 100}XX"
    for key in (range_key, range_key.lower()):
        if key in endpoint.responses:
            return True, endpoint.responses[key]
    if "default" in endpoint.responses:
        return True, endpoint.responses["default"]
    return False, None


def validate_body(schema: dict[str, Any], body: Any) -> str | None:
    """Validate a response body against a schema; return an error message or None."""
    try:
        jsonschema.validate(instance=body, schema=openapi_to_json_schema(schema))
        return None
    except jsonschema.ValidationError as exc:
        location = "/".join(str(p) for p in exc.absolute_path) or "(root)"
        return f"at {location}: {exc.message}"
    except jsonschema.SchemaError as exc:
        logger.warning("Unusable response schema, skipping validation: %s", exc)
        return None


def _slow_severity(latency_ms: float) -> str | None:
    if latency_ms >= 2 * settings.slow_threshold_ms:
        return "medium"
    if latency_ms >= settings.slow_threshold_ms:
        return "low"
    return None


def analyze_result(
    result: ExecutionResult, endpoint: EndpointInfo | None
) -> tuple[CaseResult, list[Anomaly]]:
    """Produce the pass/fail verdict and any anomalies for one execution."""
    case = result.case
    endpoint_key = f"{case.method} {case.path}"
    anomalies: list[Anomaly] = []

    if result.error is not None or result.status_code is None:
        verdict = CaseResult(
            case_id=case.id,
            name=case.name,
            category=case.category,
            endpoint=endpoint_key,
            expected_status=case.expected_status,
            actual_status=None,
            latency_ms=result.latency_ms,
            passed=False,
            failure_reason=f"request failed: {result.error}",
        )
        return verdict, anomalies

    status = result.status_code
    passed = status == case.expected_status
    failure_reason = None if passed else f"expected {case.expected_status}, got {status}"

    documented, schema = (True, None) if endpoint is None else find_declared_schema(
        endpoint, status
    )

    if status >= 500:
        anomalies.append(
            Anomaly(
                severity="critical" if not documented else "high",
                type="server_error",
                endpoint=endpoint_key,
                case_name=case.name,
                detail=(
                    f"{status} server error"
                    + ("" if documented else " (not documented in the spec)")
                    + f" — body: {str(result.response_body)[:200]}"
                ),
            )
        )
    elif not documented:
        anomalies.append(
            Anomaly(
                severity="medium",
                type="undocumented_status",
                endpoint=endpoint_key,
                case_name=case.name,
                detail=f"API returned {status}, which is not documented in the spec "
                f"(documented: {', '.join(endpoint.responses) if endpoint else '?'})",
            )
        )

    if documented and schema and result.response_body is not None:
        mismatch = validate_body(schema, result.response_body)
        if mismatch:
            anomalies.append(
                Anomaly(
                    severity="high",
                    type="schema_mismatch",
                    endpoint=endpoint_key,
                    case_name=case.name,
                    detail=f"response for status {status} does not match the documented "
                    f"schema — {mismatch}",
                )
            )

    slow = _slow_severity(result.latency_ms)
    if slow:
        anomalies.append(
            Anomaly(
                severity=slow,  # type: ignore[arg-type]
                type="slow_response",
                endpoint=endpoint_key,
                case_name=case.name,
                detail=f"response took {result.latency_ms:.0f} ms "
                f"(threshold {settings.slow_threshold_ms:.0f} ms)",
            )
        )

    verdict = CaseResult(
        case_id=case.id,
        name=case.name,
        category=case.category,
        endpoint=endpoint_key,
        expected_status=case.expected_status,
        actual_status=status,
        latency_ms=result.latency_ms,
        passed=passed,
        failure_reason=failure_reason,
    )
    return verdict, anomalies


def _dedupe(anomalies: list[Anomaly]) -> list[Anomaly]:
    """Collapse identical anomaly types repeated on the same endpoint."""
    seen: set[tuple[str, str, str]] = set()
    unique: list[Anomaly] = []
    for anomaly in anomalies:
        key = (anomaly.type, anomaly.endpoint, anomaly.severity)
        if key in seen:
            continue
        seen.add(key)
        unique.append(anomaly)
    return unique


def validate_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: turn raw execution results into verdicts + anomalies."""
    endpoints: dict[tuple[str, str], EndpointInfo] = {}
    if state.parsed_spec is not None:
        endpoints = {(e.method, e.path): e for e in state.parsed_spec.endpoints}

    case_results: list[CaseResult] = []
    anomalies: list[Anomaly] = []
    for result in state.execution_results:
        endpoint = endpoints.get((result.case.method, result.case.path))
        verdict, found = analyze_result(result, endpoint)
        case_results.append(verdict)
        anomalies.extend(found)

    anomalies = _dedupe(anomalies)
    logger.info("Validated %d results, %d anomalies", len(case_results), len(anomalies))
    return {"case_results": case_results, "anomalies": anomalies}
