"""Unit tests for the spec-parsing node (pure Python, no LLM, no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.state import AgentState
from app.nodes.spec_parser import (
    load_spec_text,
    parse_spec_node,
    parse_spec_text,
    resolve_refs,
)

PETSTORE = (Path(__file__).parent.parent / "examples" / "petstore.yaml").read_text(
    encoding="utf-8"
)


def _state(**overrides) -> AgentState:
    defaults = {"report_id": "test-run", "target_base_url": "http://example.test"}
    return AgentState(**{**defaults, **overrides})


class TestLoadSpecText:
    def test_loads_yaml(self) -> None:
        assert load_spec_text("openapi: 3.0.0")["openapi"] == "3.0.0"

    def test_loads_json(self) -> None:
        assert load_spec_text('{"openapi": "3.1.0"}')["openapi"] == "3.1.0"

    def test_rejects_garbage(self) -> None:
        with pytest.raises(ValueError):
            load_spec_text("{not valid json or yaml: [")

    def test_rejects_non_mapping(self) -> None:
        with pytest.raises(ValueError, match="top level"):
            load_spec_text("- just\n- a\n- list")


class TestResolveRefs:
    def test_inlines_local_ref(self) -> None:
        root = {
            "components": {"schemas": {"Thing": {"type": "string", "maxLength": 5}}}
        }
        resolved = resolve_refs({"$ref": "#/components/schemas/Thing"}, root)
        assert resolved == {"type": "string", "maxLength": 5}

    def test_handles_circular_refs(self) -> None:
        root = {
            "components": {
                "schemas": {
                    "Node": {
                        "type": "object",
                        "properties": {"next": {"$ref": "#/components/schemas/Node"}},
                    }
                }
            }
        }
        resolved = resolve_refs({"$ref": "#/components/schemas/Node"}, root)
        assert resolved["type"] == "object"
        assert "circular" in resolved["properties"]["next"]["description"]

    def test_unresolvable_ref_raises(self) -> None:
        with pytest.raises(ValueError, match="unresolvable"):
            resolve_refs({"$ref": "#/components/schemas/Missing"}, {})


class TestParseSpecText:
    def test_parses_petstore(self) -> None:
        spec = parse_spec_text(PETSTORE)
        assert spec.title == "Example Petstore"
        assert spec.openapi_version == "3.0.3"
        keys = {e.key for e in spec.endpoints}
        assert keys == {
            "GET /pets",
            "POST /pets",
            "GET /pets/{petId}",
            "DELETE /pets/{petId}",
        }

    def test_extracts_parameters_and_shared_path_params(self) -> None:
        spec = parse_spec_text(PETSTORE)
        get_pet = next(e for e in spec.endpoints if e.key == "GET /pets/{petId}")
        (param,) = get_pet.parameters
        assert (param.name, param.location, param.required) == ("petId", "path", True)
        assert param.param_schema == {"type": "integer", "minimum": 1}

    def test_resolves_request_body_refs(self) -> None:
        spec = parse_spec_text(PETSTORE)
        create = next(e for e in spec.endpoints if e.key == "POST /pets")
        assert create.request_body_required is True
        assert create.request_body_schema is not None
        assert "$ref" not in json.dumps(create.request_body_schema)
        assert create.request_body_schema["required"] == ["name", "species"]

    def test_extracts_response_schemas(self) -> None:
        spec = parse_spec_text(PETSTORE)
        get_pet = next(e for e in spec.endpoints if e.key == "GET /pets/{petId}")
        assert set(get_pet.responses) == {"200", "404"}
        assert get_pet.responses["200"]["required"] == ["id", "name", "species"]

    def test_detects_auth(self) -> None:
        spec = parse_spec_text(PETSTORE)
        delete = next(e for e in spec.endpoints if e.key == "DELETE /pets/{petId}")
        assert delete.auth_required is True
        assert delete.security_schemes == ["apiKey"]
        get_pets = next(e for e in spec.endpoints if e.key == "GET /pets")
        assert get_pets.auth_required is False

    def test_rejects_swagger_2(self) -> None:
        with pytest.raises(ValueError, match="Swagger 2.0"):
            parse_spec_text('{"swagger": "2.0", "info": {}, "paths": {}}')

    def test_rejects_missing_version(self) -> None:
        with pytest.raises(ValueError, match="openapi"):
            parse_spec_text('{"info": {"title": "x", "version": "1"}, "paths": {}}')

    def test_rejects_structurally_invalid_spec(self) -> None:
        # 'paths' must be an object per the OpenAPI schema.
        bad = '{"openapi": "3.0.0", "info": {"title": "x", "version": "1"}, "paths": []}'
        with pytest.raises(ValueError):
            parse_spec_text(bad)

    def test_rejects_spec_without_operations(self) -> None:
        empty = (
            '{"openapi": "3.0.0", "info": {"title": "x", "version": "1"}, "paths": {}}'
        )
        with pytest.raises(ValueError, match="no operations"):
            parse_spec_text(empty)


class TestParseSpecNode:
    def test_valid_spec_populates_state(self) -> None:
        update = parse_spec_node(_state(raw_spec=PETSTORE))
        assert "spec_error" not in update
        assert update["parsed_spec"].title == "Example Petstore"

    def test_invalid_spec_sets_error_for_conditional_edge(self) -> None:
        update = parse_spec_node(_state(raw_spec="::: not a spec :::"))
        assert "spec_error" in update
        assert "parsed_spec" not in update

    def test_missing_spec_sets_error(self) -> None:
        update = parse_spec_node(_state())
        assert "no spec provided" in update["spec_error"]

    def test_empty_raw_spec_does_not_mask_missing_url(self) -> None:
        # Browsers send an empty file part when the upload field is left blank.
        update = parse_spec_node(_state(raw_spec=""))
        assert "no spec provided" in update["spec_error"]
