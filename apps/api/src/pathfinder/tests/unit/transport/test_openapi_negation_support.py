"""The lane's predicate names the operations whose union has no complement."""

from __future__ import annotations

from assistant_core.platform.types import JSONObject

from pathfinder.main import create_app
from pathfinder.tests._support.openapi_negation import (
    labels_with_uncomplementable_union,
)

_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head", "trace")

# Two branches declare `min` and `max` at different types; the third makes the
# union wide enough that the canonical form gives up on the complement.
_RANGE_UNION: JSONObject = {
    "oneOf": [
        {
            "type": "object",
            "properties": {
                "min": {"type": "number"},
                "max": {"type": "number"},
                "type": {"const": "number-range"},
            },
        },
        {
            "type": "object",
            "properties": {
                "min": {"type": "string"},
                "max": {"type": "string"},
                "type": {"const": "date-range"},
            },
        },
        {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "type": {"const": "string"},
            },
            "required": ["value"],
        },
    ]
}

_THING: JSONObject = {"type": "object", "properties": {"a": {"type": "string"}}}


def _body_spec(schema: JSONObject, schemas: JSONObject) -> JSONObject:
    return {
        "paths": {
            "/probe": {
                "post": {
                    "requestBody": {"content": {"application/json": {"schema": schema}}}
                }
            }
        },
        "components": {"schemas": schemas},
    }


def test_a_union_of_branches_that_disagree_on_a_property_is_named() -> None:
    spec = _body_spec({"$ref": "#/components/schemas/Value"}, {"Value": _RANGE_UNION})
    assert labels_with_uncomplementable_union(spec) == frozenset({"POST /probe"})


def test_a_union_reached_through_a_property_is_named() -> None:
    body: JSONObject = {
        "type": "object",
        "properties": {"parameters": {"$ref": "#/components/schemas/Value"}},
    }
    spec = _body_spec(body, {"Value": _RANGE_UNION})
    assert labels_with_uncomplementable_union(spec) == frozenset({"POST /probe"})


def test_a_nullable_model_keeps_negative_generation() -> None:
    body: JSONObject = {
        "anyOf": [{"$ref": "#/components/schemas/Thing"}, {"type": "null"}]
    }
    spec = _body_spec(body, {"Thing": _THING})
    assert labels_with_uncomplementable_union(spec) == frozenset()


def test_a_parameter_carrying_the_union_names_its_operation() -> None:
    spec: JSONObject = {
        "paths": {
            "/probe": {
                "get": {
                    "parameters": [{"name": "q", "in": "query", "schema": _RANGE_UNION}]
                }
            }
        },
        "components": {"schemas": {}},
    }
    assert labels_with_uncomplementable_union(spec) == frozenset({"GET /probe"})


def test_the_served_spec_names_the_parameter_value_union() -> None:
    spec = create_app(include_dev_routes=False).openapi()
    labels = labels_with_uncomplementable_union(spec)
    documented = sum(
        1
        for item in spec["paths"].values()
        for method in item
        if method in _HTTP_METHODS
    )

    assert {
        "POST /api/v1/conversations",
        "POST /api/v1/conversations/step-counts",
    } <= labels
    assert "GET /api/v1/sites" not in labels
    assert "GET /health" not in labels
    # Most of the surface keeps negative generation.
    assert len(labels) * 4 < documented
