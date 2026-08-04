"""Compact textual descriptions of endpoints for LLM prompts.

Groq's free tier enforces token-per-minute limits, so prompts summarize
schemas instead of embedding full JSON documents.
"""

from __future__ import annotations

from typing import Any

from app.models.spec import EndpointInfo

_MAX_DEPTH = 3
_MAX_FIELDS = 12

_CONSTRAINT_KEYS = (
    "format",
    "enum",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
)


def summarize_schema(schema: dict[str, Any] | None, depth: int = 0) -> str:
    """Render a JSON schema as a compact, human/LLM-readable type expression."""
    if not isinstance(schema, dict) or not schema:
        return "any"
    if depth >= _MAX_DEPTH:
        return "..."

    for combiner in ("oneOf", "anyOf", "allOf"):
        variants = schema.get(combiner)
        if isinstance(variants, list) and variants:
            parts = [summarize_schema(v, depth + 1) for v in variants[:4]]
            return f"{combiner}({' | '.join(parts)})"

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = "|".join(str(t) for t in schema_type)

    constraints = []
    for key in _CONSTRAINT_KEYS:
        if key in schema:
            value = schema[key]
            if key == "enum" and isinstance(value, list):
                value = "|".join(str(v) for v in value[:8])
            constraints.append(f"{key}={value}")
    if schema.get("nullable"):
        constraints.append("nullable")
    suffix = f" [{', '.join(constraints)}]" if constraints else ""

    if schema_type == "object" or "properties" in schema:
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        fields = []
        for i, (name, sub) in enumerate(props.items()):
            if i >= _MAX_FIELDS:
                fields.append("...")
                break
            marker = "*" if name in required else ""
            fields.append(f"{name}{marker}: {summarize_schema(sub, depth + 1)}")
        return "{" + ", ".join(fields) + "}" + suffix
    if schema_type == "array":
        return f"array<{summarize_schema(schema.get('items'), depth + 1)}>{suffix}"
    return f"{schema_type or 'any'}{suffix}"


def describe_endpoint(endpoint: EndpointInfo) -> str:
    """One compact multi-line description of an endpoint for prompts."""
    lines = [f"{endpoint.method} {endpoint.path}"]
    if endpoint.summary:
        lines.append(f"  summary: {endpoint.summary[:120]}")
    if endpoint.parameters:
        rendered = []
        for param in endpoint.parameters:
            required = "required" if param.required else "optional"
            rendered.append(
                f"{param.name} ({param.location}, {required}, "
                f"{summarize_schema(param.param_schema, depth=1)})"
            )
        lines.append(f"  params: {'; '.join(rendered)}")
    if endpoint.request_body_schema is not None:
        required = "required" if endpoint.request_body_required else "optional"
        lines.append(
            f"  body ({required}): {summarize_schema(endpoint.request_body_schema)}"
        )
    documented = ", ".join(endpoint.responses.keys()) or "none documented"
    lines.append(f"  documented statuses: {documented}")
    if endpoint.auth_required:
        lines.append(f"  auth: required ({', '.join(endpoint.security_schemes)})")
    else:
        lines.append("  auth: none")
    return "\n".join(lines)


def batched(items: list, size: int) -> list[list]:
    """Split ``items`` into consecutive chunks of at most ``size``."""
    return [items[i : i + size] for i in range(0, len(items), size)]
