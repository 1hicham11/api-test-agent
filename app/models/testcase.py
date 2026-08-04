"""Concrete, executable test cases and their execution results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.plan import TestCategory


class GeneratedCase(BaseModel):
    """LLM output: one concrete HTTP request plus the status it should get.

    All parameter values are strings and the body is a JSON-encoded string —
    this keeps the schema simple enough for reliable structured output.
    """

    name: str = Field(description="Short snake_case test name")
    category: TestCategory
    method: str = Field(description="Upper-case HTTP method")
    path: str = Field(description="Templated path exactly as in the spec, e.g. /pets/{petId}")
    path_params: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = Field(
        default=None, description="JSON-encoded request body, or null for no body"
    )
    expected_status: int


class GeneratedCaseList(BaseModel):
    """LLM output wrapper: cases for a batch of endpoints."""

    cases: list[GeneratedCase] = Field(default_factory=list)


class TestCase(GeneratedCase):
    """A generated case with a stable id, ready for execution."""

    __test__ = False  # keep pytest from collecting this model as a test class

    id: str


class ExecutionResult(BaseModel):
    """Raw outcome of running one test case against the target API."""

    case: TestCase
    status_code: int | None = None
    latency_ms: float = 0.0
    response_body: Any | None = None
    error: str | None = Field(
        default=None, description="Transport-level error if the request never completed"
    )
