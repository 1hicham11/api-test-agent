"""Structured-output models for the LLM test-planning node."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TestCategory = Literal["nominal", "edge", "negative"]


class PlannedCase(BaseModel):
    """One test idea for an endpoint, before concrete data is generated."""

    name: str = Field(description="Short snake_case test name")
    category: TestCategory
    description: str = Field(description="What the test does and why, one sentence")
    expected_status: int = Field(description="HTTP status code the API should return")


class EndpointTestPlan(BaseModel):
    """The set of planned cases for one endpoint."""

    method: str
    path: str
    cases: list[PlannedCase] = Field(default_factory=list)


class TestPlanBatch(BaseModel):
    """LLM output wrapper: plans for a batch of endpoints."""

    plans: list[EndpointTestPlan] = Field(default_factory=list)
