"""Models describing a parsed OpenAPI specification."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ParameterInfo(BaseModel):
    """A single operation parameter (query, path, header or cookie)."""

    name: str
    location: str = Field(description="One of: query, path, header, cookie")
    required: bool = False
    param_schema: dict[str, Any] | None = None
    description: str | None = None


class EndpointInfo(BaseModel):
    """One operation (method + path) extracted from the spec."""

    method: str = Field(description="Upper-case HTTP method, e.g. GET")
    path: str = Field(description="Templated path, e.g. /pets/{petId}")
    operation_id: str | None = None
    summary: str | None = None
    parameters: list[ParameterInfo] = Field(default_factory=list)
    request_body_schema: dict[str, Any] | None = None
    request_body_required: bool = False
    responses: dict[str, dict[str, Any] | None] = Field(
        default_factory=dict,
        description="Documented status code (or 'default'/'4XX') -> resolved JSON body schema, if any",
    )
    auth_required: bool = False
    security_schemes: list[str] = Field(default_factory=list)

    @property
    def key(self) -> str:
        """Stable identifier, e.g. ``GET /pets/{petId}``."""
        return f"{self.method} {self.path}"


class ParsedSpec(BaseModel):
    """Everything the downstream nodes need from the OpenAPI document."""

    title: str
    version: str
    openapi_version: str
    endpoints: list[EndpointInfo] = Field(default_factory=list)
    notes: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings raised while parsing (e.g. endpoint cap applied)",
    )
