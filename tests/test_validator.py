"""Unit tests for the validation & anomaly node (pure Python, no LLM)."""

from __future__ import annotations

from app.models.spec import EndpointInfo
from app.models.state import AgentState
from app.models.testcase import ExecutionResult, TestCase
from app.nodes.validator import (
    analyze_result,
    find_declared_schema,
    openapi_to_json_schema,
    validate_node,
)

PET_SCHEMA = {
    "type": "object",
    "required": ["id", "name"],
    "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
}

ENDPOINT = EndpointInfo(
    method="GET",
    path="/pets/{petId}",
    responses={"200": PET_SCHEMA, "404": None},
)


def _case(**overrides) -> TestCase:
    defaults = {
        "id": "case-0001",
        "name": "get_pet",
        "category": "nominal",
        "method": "GET",
        "path": "/pets/{petId}",
        "path_params": {"petId": "1"},
        "expected_status": 200,
    }
    return TestCase(**{**defaults, **overrides})


def _result(**overrides) -> ExecutionResult:
    defaults = {
        "case": _case(),
        "status_code": 200,
        "latency_ms": 50.0,
        "response_body": {"id": 1, "name": "Rex"},
    }
    return ExecutionResult(**{**defaults, **overrides})


class TestSchemaConversion:
    def test_nullable_becomes_type_union(self) -> None:
        converted = openapi_to_json_schema({"type": "string", "nullable": True})
        assert converted == {"type": ["string", "null"]}

    def test_boolean_exclusive_minimum(self) -> None:
        converted = openapi_to_json_schema(
            {"type": "number", "minimum": 0, "exclusiveMinimum": True}
        )
        assert converted == {"type": "number", "exclusiveMinimum": 0}

    def test_nested_conversion(self) -> None:
        converted = openapi_to_json_schema(
            {"type": "object", "properties": {"tag": {"type": "string", "nullable": True}}}
        )
        assert converted["properties"]["tag"]["type"] == ["string", "null"]


class TestFindDeclaredSchema:
    def test_exact_status(self) -> None:
        assert find_declared_schema(ENDPOINT, 200) == (True, PET_SCHEMA)

    def test_undocumented_status(self) -> None:
        assert find_declared_schema(ENDPOINT, 500) == (False, None)

    def test_range_key(self) -> None:
        endpoint = EndpointInfo(method="GET", path="/x", responses={"4XX": None})
        assert find_declared_schema(endpoint, 404) == (True, None)

    def test_default_key(self) -> None:
        endpoint = EndpointInfo(method="GET", path="/x", responses={"default": None})
        assert find_declared_schema(endpoint, 503) == (True, None)


class TestAnalyzeResult:
    def test_passing_nominal_case(self) -> None:
        verdict, anomalies = analyze_result(_result(), ENDPOINT)
        assert verdict.passed is True
        assert anomalies == []

    def test_status_mismatch_fails(self) -> None:
        verdict, _ = analyze_result(_result(status_code=404, response_body=None), ENDPOINT)
        assert verdict.passed is False
        assert "expected 200, got 404" in verdict.failure_reason

    def test_undocumented_500_is_critical(self) -> None:
        _, anomalies = analyze_result(
            _result(status_code=500, response_body={"detail": "boom"}), ENDPOINT
        )
        (anomaly,) = anomalies
        assert anomaly.type == "server_error"
        assert anomaly.severity == "critical"

    def test_documented_500_is_high(self) -> None:
        endpoint = EndpointInfo(method="GET", path="/x", responses={"500": None})
        _, anomalies = analyze_result(_result(status_code=500), endpoint)
        (anomaly,) = anomalies
        assert anomaly.type == "server_error"
        assert anomaly.severity == "high"

    def test_undocumented_status_flagged(self) -> None:
        _, anomalies = analyze_result(
            _result(status_code=418, response_body=None), ENDPOINT
        )
        assert any(a.type == "undocumented_status" and a.severity == "medium" for a in anomalies)

    def test_schema_mismatch_flagged(self) -> None:
        bad_body = {"id": "not-an-int", "name": "Rex"}
        _, anomalies = analyze_result(_result(response_body=bad_body), ENDPOINT)
        (anomaly,) = anomalies
        assert anomaly.type == "schema_mismatch"
        assert anomaly.severity == "high"
        assert "at id" in anomaly.detail

    def test_missing_required_field_flagged(self) -> None:
        _, anomalies = analyze_result(_result(response_body={"id": 1}), ENDPOINT)
        assert any(a.type == "schema_mismatch" for a in anomalies)

    def test_slow_response_flagged(self) -> None:
        _, anomalies = analyze_result(_result(latency_ms=1500.0), ENDPOINT)
        assert any(a.type == "slow_response" and a.severity == "low" for a in anomalies)

    def test_very_slow_response_is_medium(self) -> None:
        _, anomalies = analyze_result(_result(latency_ms=2500.0), ENDPOINT)
        assert any(a.type == "slow_response" and a.severity == "medium" for a in anomalies)

    def test_transport_error_fails_without_anomaly(self) -> None:
        result = ExecutionResult(case=_case(), error="ConnectError: refused")
        verdict, anomalies = analyze_result(result, ENDPOINT)
        assert verdict.passed is False
        assert "request failed" in verdict.failure_reason
        assert anomalies == []


class TestValidateNode:
    def test_aggregates_and_dedupes(self) -> None:
        state = AgentState(
            report_id="r1",
            target_base_url="http://example.test",
            execution_results=[
                _result(),
                _result(status_code=500, case=_case(name="a", id="case-0002")),
                _result(status_code=500, case=_case(name="b", id="case-0003")),
            ],
        )
        update = validate_node(state)
        assert len(update["case_results"]) == 3
        server_errors = [a for a in update["anomalies"] if a.type == "server_error"]
        assert len(server_errors) == 1  # deduped per endpoint+type+severity
