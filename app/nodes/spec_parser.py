"""Spec-parsing node: load, validate and flatten an OpenAPI 3.x document.

Pure Python — no LLM involved. Uses ``openapi-spec-validator`` for structural
validation plus custom extraction of endpoints, parameters, schemas and auth.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import yaml
from openapi_spec_validator import validate as validate_openapi

from app.config import settings
from app.models.spec import EndpointInfo, ParameterInfo, ParsedSpec
from app.models.state import AgentState

logger = logging.getLogger(__name__)

_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def load_spec_text(text: str) -> dict[str, Any]:
    """Parse raw spec text as JSON first, then YAML.

    Raises:
        ValueError: if the text is neither valid JSON nor valid YAML mapping.
    """
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"spec is neither valid JSON nor valid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError("spec must be a JSON/YAML object at the top level")
    return loaded


def _lookup_ref(root: dict[str, Any], ref: str) -> Any:
    """Resolve a local ``#/...`` JSON pointer against the document root."""
    node: Any = root
    for part in ref.lstrip("#/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"unresolvable $ref: {ref}")
        node = node[part]
    return node


def resolve_refs(obj: Any, root: dict[str, Any], _seen: tuple[str, ...] = ()) -> Any:
    """Recursively inline local ``$ref`` pointers, guarding against cycles."""
    if isinstance(obj, dict):
        ref = obj.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            if ref in _seen:
                return {"description": f"(circular reference to {ref})"}
            target = resolve_refs(_lookup_ref(root, ref), root, _seen + (ref,))
            if isinstance(target, dict):
                siblings = {k: v for k, v in obj.items() if k != "$ref"}
                return {**target, **resolve_refs(siblings, root, _seen)}
            return target
        return {k: resolve_refs(v, root, _seen) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_refs(item, root, _seen) for item in obj]
    return obj


def _json_content_schema(content: dict[str, Any] | None) -> dict[str, Any] | None:
    """Pick the JSON media-type schema out of an OpenAPI ``content`` map."""
    if not isinstance(content, dict) or not content:
        return None
    for media_type, media in content.items():
        if "json" in media_type and isinstance(media, dict):
            schema = media.get("schema")
            return schema if isinstance(schema, dict) else None
    first = next(iter(content.values()))
    if isinstance(first, dict) and isinstance(first.get("schema"), dict):
        return first["schema"]
    return None


def _extract_parameters(raw_params: list[Any]) -> list[ParameterInfo]:
    """Convert already-resolved OpenAPI parameter objects to models."""
    params: list[ParameterInfo] = []
    for raw in raw_params:
        if not isinstance(raw, dict) or "name" not in raw or "in" not in raw:
            continue
        params.append(
            ParameterInfo(
                name=str(raw["name"]),
                location=str(raw["in"]),
                required=bool(raw.get("required", raw.get("in") == "path")),
                param_schema=raw.get("schema") if isinstance(raw.get("schema"), dict) else None,
                description=raw.get("description"),
            )
        )
    return params


def _extract_security(operation: dict[str, Any], root: dict[str, Any]) -> tuple[bool, list[str]]:
    """Determine whether an operation requires auth and which schemes apply."""
    security = operation.get("security", root.get("security"))
    if not isinstance(security, list) or not security:
        return False, []
    schemes: list[str] = []
    for requirement in security:
        if isinstance(requirement, dict):
            schemes.extend(requirement.keys())
    return bool(schemes), sorted(set(schemes))


def extract_endpoints(spec: dict[str, Any]) -> list[EndpointInfo]:
    """Flatten the spec's ``paths`` object into a list of endpoints."""
    endpoints: list[EndpointInfo] = []
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return endpoints

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        path_item = resolve_refs(path_item, spec)
        shared_params = path_item.get("parameters", [])
        for method in _HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            merged: dict[tuple[str, str], Any] = {}
            for raw in list(shared_params) + list(operation.get("parameters", [])):
                if isinstance(raw, dict) and "name" in raw and "in" in raw:
                    merged[(str(raw["name"]), str(raw["in"]))] = raw

            request_body = operation.get("requestBody")
            body_schema: dict[str, Any] | None = None
            body_required = False
            if isinstance(request_body, dict):
                body_schema = _json_content_schema(request_body.get("content"))
                body_required = bool(request_body.get("required", False))

            responses: dict[str, dict[str, Any] | None] = {}
            for status, response in (operation.get("responses") or {}).items():
                if isinstance(response, dict):
                    responses[str(status)] = _json_content_schema(response.get("content"))

            auth_required, schemes = _extract_security(operation, spec)
            endpoints.append(
                EndpointInfo(
                    method=method.upper(),
                    path=str(path),
                    operation_id=operation.get("operationId"),
                    summary=operation.get("summary") or operation.get("description"),
                    parameters=_extract_parameters(list(merged.values())),
                    request_body_schema=body_schema,
                    request_body_required=body_required,
                    responses=responses,
                    auth_required=auth_required,
                    security_schemes=schemes,
                )
            )
    return endpoints


def parse_spec_text(text: str) -> ParsedSpec:
    """Parse and validate raw spec text into a :class:`ParsedSpec`.

    Raises:
        ValueError: on invalid documents (bad syntax, wrong version,
            failed OpenAPI validation, or no endpoints).
    """
    spec = load_spec_text(text)

    if "swagger" in spec and "openapi" not in spec:
        raise ValueError(
            f"Swagger {spec.get('swagger')} specs are not supported; "
            "please convert to OpenAPI 3.x (e.g. with swagger2openapi)."
        )
    openapi_version = str(spec.get("openapi", ""))
    if not openapi_version.startswith("3"):
        raise ValueError(
            f"unsupported or missing 'openapi' version {openapi_version!r}; expected 3.x"
        )

    try:
        validate_openapi(spec)
    except Exception as exc:  # validator raises several error types
        raise ValueError(f"OpenAPI validation failed: {exc}") from exc

    endpoints = extract_endpoints(spec)
    if not endpoints:
        raise ValueError("spec contains no operations under 'paths'")

    notes: list[str] = []
    if len(endpoints) > settings.max_endpoints:
        notes.append(
            f"Spec has {len(endpoints)} operations; analyzing the first "
            f"{settings.max_endpoints} (AGENT_MAX_ENDPOINTS)."
        )
        endpoints = endpoints[: settings.max_endpoints]

    info = spec.get("info") or {}
    return ParsedSpec(
        title=str(info.get("title", "Untitled API")),
        version=str(info.get("version", "0")),
        openapi_version=openapi_version,
        endpoints=endpoints,
        notes=notes,
    )


def parse_spec_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: load the spec (from text or URL) and parse it.

    On any failure sets ``spec_error`` so the conditional edge routes to the
    error-explanation node instead of continuing the pipeline.
    """
    text = state.raw_spec or None
    if text is None and state.spec_url:
        try:
            response = httpx.get(state.spec_url, timeout=settings.request_timeout, follow_redirects=True)
            response.raise_for_status()
            text = response.text
        except httpx.HTTPError as exc:
            return {"spec_error": f"could not fetch spec from {state.spec_url}: {exc}"}
    if not text:
        return {"spec_error": "no spec provided (need spec file content or spec URL)"}

    try:
        parsed = parse_spec_text(text)
    except ValueError as exc:
        return {"spec_error": str(exc)}

    logger.info("Parsed spec '%s': %d endpoints", parsed.title, len(parsed.endpoints))
    return {"parsed_spec": parsed, "notes": state.notes + parsed.notes}
