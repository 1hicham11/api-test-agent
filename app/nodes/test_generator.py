"""Test-generation node (LLM): turn planned cases into concrete HTTP requests.

Plans are processed in batches (map pattern), mirroring the planner.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.llm import LLMError, invoke_structured
from app.models.plan import EndpointTestPlan
from app.models.spec import EndpointInfo
from app.models.state import AgentState
from app.models.testcase import GeneratedCaseList, TestCase
from app.nodes.prompting import batched, describe_endpoint

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an expert API test engineer. You turn test plans into concrete, "
    "executable HTTP requests with realistic fake data that respects every "
    "schema constraint (formats, enums, min/max, required fields). Always "
    "return the requested structured data, nothing else."
)

_INSTRUCTIONS = """Convert EVERY planned case below into one concrete test case.
Rules:
- 'method' and 'path' must be copied EXACTLY from the endpoint (keep {placeholders} in path).
- Provide a value in path_params for every {placeholder} in the path.
- 'body' must be a JSON-encoded STRING (e.g. "{\\"name\\": \\"Dune\\"}") or null.
- Respect schema constraints: string formats (email, uuid, date-time), enums,
  minimum/maximum, minLength/maxLength. Use realistic values (real-looking names,
  emails, ISO dates), not "string" or "test".
- For negative cases, break exactly what the plan describes (omit a required field,
  send a wrong type, use a nonexistent id like 999999, or set an invalid
  Authorization header) and set the matching expected_status.
- Only set headers when the case needs them (e.g. Authorization for auth cases).
- Copy each case's expected_status from its plan.

"""


def _describe_plan(endpoint: EndpointInfo, plan: EndpointTestPlan) -> str:
    lines = [describe_endpoint(endpoint), "  planned cases:"]
    for case in plan.cases:
        lines.append(
            f"    - {case.name} ({case.category}, expect {case.expected_status}): "
            f"{case.description}"
        )
    return "\n".join(lines)


def generate_tests_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: produce executable :class:`TestCase` objects."""
    assert state.parsed_spec is not None, "generator requires a parsed spec"
    endpoints = {(e.method, e.path): e for e in state.parsed_spec.endpoints}
    notes = list(state.notes)
    cases: list[TestCase] = []

    plans_with_endpoints = [
        (endpoints[(p.method, p.path)], p)
        for p in state.test_plans
        if (p.method, p.path) in endpoints
    ]

    for batch in batched(plans_with_endpoints, settings.batch_size):
        prompt = _INSTRUCTIONS + "\n\n".join(_describe_plan(e, p) for e, p in batch)
        try:
            result = invoke_structured(_SYSTEM, prompt, GeneratedCaseList)
        except LLMError as exc:
            logger.error("Generation batch failed: %s", exc)
            notes.append(f"LLM generation failed for a batch of {len(batch)} plans: {exc}")
            continue

        batch_keys = {(e.method, e.path) for e, _ in batch}
        for generated in result.cases:
            key = (generated.method.upper(), generated.path)
            if key not in batch_keys:
                notes.append(
                    f"Dropped generated case '{generated.name}': unknown endpoint "
                    f"{generated.method} {generated.path}"
                )
                continue
            generated.method = generated.method.upper()
            cases.append(
                TestCase(id=f"case-{len(cases) + 1:04d}", **generated.model_dump())
            )

    logger.info("Generated %d executable test cases", len(cases))
    if not cases:
        notes.append("No executable test cases were generated.")
    return {"test_cases": cases, "notes": notes}
