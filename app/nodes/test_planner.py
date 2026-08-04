"""Test-planning node (LLM): decide WHAT to test for each endpoint.

Endpoints are processed in batches (map pattern) to keep each prompt small.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.llm import LLMError, invoke_structured
from app.models.plan import EndpointTestPlan, PlannedCase, TestPlanBatch
from app.models.spec import EndpointInfo
from app.models.state import AgentState
from app.nodes.prompting import batched, describe_endpoint

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an expert API test engineer. You design concise, high-value test "
    "plans for HTTP endpoints described by an OpenAPI spec. Always return the "
    "requested structured data, nothing else."
)

_INSTRUCTIONS = """For EACH endpoint below, produce a test plan with 3 to 5 cases:
- at least 1 nominal case (valid, realistic inputs; expect the documented success status),
- at least 1 edge case (boundary values: min/max lengths, limits, empty strings, zero),
- at least 1 negative case (missing required field, wrong type, nonexistent resource id,
  or invalid/missing auth when the endpoint requires auth).
Rules:
- 'method' and 'path' must be copied EXACTLY from the endpoint heading.
- expected_status must be realistic: prefer documented statuses; use 422 for body
  validation errors on FastAPI-style APIs, 404 for unknown ids, 401/403 for auth failures.
- Keep names short snake_case and descriptions one sentence.

Endpoints:
"""


def _fallback_plan(endpoint: EndpointInfo) -> EndpointTestPlan:
    """Minimal deterministic plan used when the LLM fails for a batch."""
    success = next(
        (int(s) for s in endpoint.responses if s.isdigit() and s.startswith("2")), 200
    )
    return EndpointTestPlan(
        method=endpoint.method,
        path=endpoint.path,
        cases=[
            PlannedCase(
                name="nominal_request",
                category="nominal",
                description="Call the endpoint with valid, realistic inputs.",
                expected_status=success,
            )
        ],
    )


def plan_tests_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: build an :class:`EndpointTestPlan` per endpoint."""
    assert state.parsed_spec is not None, "planner requires a parsed spec"
    endpoints = state.parsed_spec.endpoints
    plans: list[EndpointTestPlan] = []
    notes = list(state.notes)
    known = {(e.method, e.path) for e in endpoints}

    for batch in batched(endpoints, settings.batch_size):
        prompt = _INSTRUCTIONS + "\n\n".join(describe_endpoint(e) for e in batch)
        try:
            result = invoke_structured(_SYSTEM, prompt, TestPlanBatch)
        except LLMError as exc:
            logger.error("Planning batch failed: %s", exc)
            notes.append(f"LLM planning failed for a batch of {len(batch)} endpoints: {exc}")
            plans.extend(_fallback_plan(e) for e in batch)
            continue

        planned = {(p.method.upper(), p.path): p for p in result.plans if p.cases}
        for endpoint in batch:
            plan = planned.get((endpoint.method, endpoint.path))
            if plan is None:
                notes.append(f"LLM returned no plan for {endpoint.key}; using fallback")
                plan = _fallback_plan(endpoint)
            plan.method = endpoint.method
            plans.append(plan)

    total_cases = sum(len(p.cases) for p in plans)
    logger.info("Planned %d cases across %d endpoints", total_cases, len(plans))
    # Drop any hallucinated endpoints that don't exist in the spec.
    plans = [p for p in plans if (p.method, p.path) in known]
    return {"test_plans": plans, "notes": notes}
