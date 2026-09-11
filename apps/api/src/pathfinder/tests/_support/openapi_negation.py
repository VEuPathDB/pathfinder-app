"""The operations whose request schema carries a union with no complement.

Negative-case generation bars a keyword and draws from the complement. The
canonical form cannot spell the complement of a union whose branches declare
the same property name at different types, so those operations are fuzzed
with positive cases only.
"""

from __future__ import annotations

from collections.abc import Iterator

import jsonschema_rs
from assistant_core.platform.types import JSONObject
from jsonschema_rs import canonical
from pydantic import BaseModel, ConfigDict, Field, JsonValue

_HTTP_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
)
_UNION_KEYWORDS = ("oneOf", "anyOf")
_COMPONENT_PREFIX = "#/components/schemas/"
_DEFS_PREFIX = "#/$defs/"


class _Parameter(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parameter_schema: JSONObject = Field(default_factory=dict, alias="schema")


class _MediaType(BaseModel):
    model_config = ConfigDict(extra="ignore")

    media_schema: JSONObject = Field(default_factory=dict, alias="schema")


class _RequestBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: dict[str, _MediaType] = Field(default_factory=dict)


class _Operation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parameters: list[_Parameter] = Field(default_factory=list)
    request_body: _RequestBody | None = Field(default=None, alias="requestBody")

    def request_schemas(self) -> list[JSONObject]:
        schemas = [parameter.parameter_schema for parameter in self.parameters]
        if self.request_body is not None:
            schemas.extend(
                media.media_schema for media in self.request_body.content.values()
            )
        return schemas


class _Components(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schemas: dict[str, JSONObject] = Field(default_factory=dict)


class _Document(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paths: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)
    components: _Components = Field(default_factory=_Components)

    def operations(self) -> Iterator[tuple[str, _Operation]]:
        for path, item in self.paths.items():
            for method, operation in item.items():
                if method in _HTTP_METHODS:
                    yield (
                        f"{method.upper()} {path}",
                        _Operation.model_validate(operation),
                    )


def _referenced_name(node: JsonValue) -> str | None:
    match node:
        case {"$ref": str(uri)} if uri.startswith(_COMPONENT_PREFIX):
            return uri.removeprefix(_COMPONENT_PREFIX)
        case _:
            return None


def _rewritten_object(node: JSONObject) -> JSONObject:
    """The object with every component pointer moved to the carried definitions."""
    name = _referenced_name(node)
    if name is not None:
        return {"$ref": _DEFS_PREFIX + name}
    return {key: _rewritten(value) for key, value in node.items()}


def _rewritten(node: JsonValue) -> JsonValue:
    """The node with every component pointer moved to the carried definitions."""
    match node:
        case dict():
            return _rewritten_object(node)
        case list():
            return [_rewritten(item) for item in node]
        case _:
            return node


def _collect(node: JsonValue, schemas: dict[str, JSONObject], out: JSONObject) -> None:
    """Every component schema the node reaches, directly or through another."""
    match node:
        case dict():
            name = _referenced_name(node)
            if name is not None and name not in out:
                out[name] = schemas[name]
                _collect(schemas[name], schemas, out)
            for key, value in node.items():
                if key != "$ref":
                    _collect(value, schemas, out)
        case list():
            for item in node:
                _collect(item, schemas, out)
        case _:
            return


def _has_no_complement(union: JSONObject, schemas: dict[str, JSONObject]) -> bool:
    carried: JSONObject = {}
    _collect(union, schemas, carried)
    document = _rewritten_object({**union, "$defs": carried})
    try:
        negated = jsonschema_rs.canonicalize(document).negate()
    except canonical.CanonicalizationError:
        return True
    # Negation declines in place by handing back a bar over its own input.
    return type(negated.view()) is canonical.NotView


def _unions(
    node: JsonValue, schemas: dict[str, JSONObject], seen: set[str]
) -> Iterator[JSONObject]:
    """Every union the walk reaches, as the one keyword a mutation bars."""
    match node:
        case dict():
            for keyword in _UNION_KEYWORDS:
                if keyword in node:
                    yield {keyword: node[keyword]}
            name = _referenced_name(node)
            if name is not None and name not in seen:
                seen.add(name)
                yield from _unions(schemas[name], schemas, seen)
            for key, value in node.items():
                if key != "$ref":
                    yield from _unions(value, schemas, seen)
        case list():
            for item in node:
                yield from _unions(item, schemas, seen)
        case _:
            return


def labels_with_uncomplementable_union(spec: JSONObject) -> frozenset[str]:
    """The labels of the operations whose request schema has no complement."""
    document = _Document.model_validate(spec)
    schemas = document.components.schemas
    labels: set[str] = set()
    for label, operation in document.operations():
        seen: set[str] = set()
        for root in operation.request_schemas():
            for union in _unions(root, schemas, seen):
                if _has_no_complement(union, schemas):
                    labels.add(label)
    return frozenset(labels)
