"""Each value of a typed answer as a statistic row, in the display form its schema type gives it."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    field_validator,
)

from pathfinder.domain.audit.facts import CODE_WORDS, YES_NO
from pathfinder.domain.statistic_facts import StatisticRowFact

type LeafKind = Literal["number", "share", "boolean", "words", "string", "sentence"]

_JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
_SCALARS: Mapping[str, LeafKind] = {
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
    "string": "string",
}
_FORMATS: Mapping[str, LeafKind] = {"share": "share", "sentence": "sentence"}


class NoDisplayFormError(ValueError):
    def __init__(self, path: str, what: str) -> None:
        super().__init__(f"{path or 'the root'}: no display form for {what}")


def _path(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


class SchemaNode(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    ref: str | None = Field(default=None, alias="$ref")
    kind: str | None = Field(default=None, alias="type")
    title: str | None = None
    format: str | None = None
    enum: tuple[JsonValue, ...] = ()
    const: JsonValue = None
    properties: dict[str, SchemaNode] = Field(default_factory=dict)
    items: SchemaNode | None = None
    prefix_items: tuple[SchemaNode, ...] = Field(default=(), alias="prefixItems")
    additional_properties: SchemaNode | None = Field(
        default=None, alias="additionalProperties"
    )
    any_of: tuple[SchemaNode, ...] = Field(default=(), alias="anyOf")
    one_of: tuple[SchemaNode, ...] = Field(default=(), alias="oneOf")
    defs: dict[str, SchemaNode] = Field(default_factory=dict, alias="$defs")

    @field_validator("additional_properties", mode="before")
    @classmethod
    def _closed_is_none(cls, value: JsonValue) -> JsonValue:
        return None if value is True or value is False else value

    @property
    def codes(self) -> tuple[JsonValue, ...]:
        return (self.const,) if "const" in self.model_fields_set else self.enum

    def names(self, value: JsonValue) -> bool:
        return value in self.codes

    def words(self, code: str) -> str:
        if self.title in CODE_WORDS and code in CODE_WORDS[self.title]:
            return CODE_WORDS[self.title][code]
        spaced = code.replace("_", " ")
        coded = any("_" in str(member) for member in self.codes)
        return spaced.lower() if coded and code.isupper() else spaced

    def members(self) -> tuple[SchemaNode, ...]:
        return (*self.any_of, *self.one_of)

    def children(self, path: str) -> list[tuple[str, SchemaNode]] | None:
        if self.kind == "array":
            items = (*self.prefix_items, *(() if self.items is None else (self.items,)))
            if not items:
                raise NoDisplayFormError(path, "the items")
            return [(_path(path, "*"), item) for item in items]
        if self.kind != "object" and not self.properties:
            return None
        named = [(_path(path, key), child) for key, child in self.properties.items()]
        mapped = (
            []
            if self.additional_properties is None
            else [(_path(path, "*"), self.additional_properties)]
        )
        if not named and not mapped:
            raise NoDisplayFormError(path, "the object")
        return [*named, *mapped]

    def leaf_kind(self, path: str) -> LeafKind | None:
        if self.codes:
            return "words"
        if self.kind == "null":
            return None
        if self.kind is None or self.kind not in _SCALARS:
            schema = self.model_dump_json(by_alias=True, exclude_defaults=True)
            raise NoDisplayFormError(path, f"the schema {schema}")
        if self.format is not None and self.format in _FORMATS:
            return _FORMATS[self.format]
        return _SCALARS[self.kind]


_UNTYPED = SchemaNode()


def _number(value: float, branches: Sequence[SchemaNode]) -> str:
    if any(branch.format == "share" for branch in branches):
        return f"{round(value * 100, 1):g}%"
    return json.dumps(value)


def _scalar(
    path: str, branches: Sequence[SchemaNode], value: JsonValue
) -> StatisticRowFact:
    named = next((b for b in branches if b.names(value)), None)
    match value:
        case bool():
            return StatisticRowFact(name=path, value=YES_NO[value], form="word")
        case int() | float():
            return StatisticRowFact(name=path, value=_number(value, branches))
        case str() if named is not None:
            words = named.words(value)
            return StatisticRowFact(name=path, value=words, form="word", code=value)
        case str() if any(branch.format == "sentence" for branch in branches):
            return StatisticRowFact(name=path, value=value, form="sentence")
        case _:
            return StatisticRowFact(name=path, value=str(value), form="word")


@dataclass(frozen=True)
class FactSchema:
    root: SchemaNode
    leaves: tuple[tuple[str, LeafKind], ...]

    def _resolved(self, node: SchemaNode) -> SchemaNode:
        while node.ref is not None:
            node = self.root.defs[node.ref.rsplit("/", 1)[-1]]
        return node

    def _branches(self, node: SchemaNode) -> list[SchemaNode]:
        held = self._resolved(node)
        members = held.members()
        if not members:
            return [held]
        return [branch for member in members for branch in self._branches(member)]

    def _fits(self, branch: SchemaNode, value: Mapping[str, JsonValue]) -> bool:
        if not branch.properties or not set(value) <= set(branch.properties):
            return False
        held = {key: self._resolved(branch.properties[key]) for key in value}
        return all(node.names(value[key]) for key, node in held.items() if node.codes)

    def _object(
        self, branches: Sequence[SchemaNode], value: Mapping[str, JsonValue]
    ) -> SchemaNode:
        fitting = [b for b in branches if self._fits(b, value)]
        held = [*fitting, *branches]
        return held[0] if held else _UNTYPED

    def _field(self, branch: SchemaNode, key: str) -> SchemaNode:
        if key in branch.properties:
            return branch.properties[key]
        return branch.additional_properties or _UNTYPED

    def _item(self, branches: Sequence[SchemaNode], index: int) -> SchemaNode:
        array = next((b for b in branches if b.kind == "array"), _UNTYPED)
        if index < len(array.prefix_items):
            return array.prefix_items[index]
        return array.items or _UNTYPED

    def rows(
        self, node: SchemaNode, value: JsonValue, path: str
    ) -> Iterator[StatisticRowFact]:
        branches = self._branches(node)
        match value:
            case None:
                return
            case dict():
                branch = self._object(branches, value)
                for key, item in value.items():
                    yield from self.rows(
                        self._field(branch, key), item, _path(path, key)
                    )
            case list():
                for index, item in enumerate(value):
                    yield from self.rows(
                        self._item(branches, index), item, _path(path, str(index))
                    )
            case _:
                yield _scalar(path, branches, value)


def _leaves(
    root: SchemaNode, node: SchemaNode, path: str, seen: frozenset[str]
) -> Iterator[tuple[str, LeafKind]]:
    if node.ref is not None:
        name = node.ref.rsplit("/", 1)[-1]
        if name not in seen:
            yield from _leaves(root, root.defs[name], path, seen | {name})
        return
    members = node.members()
    children = None if members else node.children(path)
    if not members and children is None:
        kind = node.leaf_kind(path)
        if kind is not None:
            yield path, kind
        return
    for child_path, child in children or [(path, m) for m in members]:
        yield from _leaves(root, child, child_path, seen)


@cache
def fact_schema(source: type[BaseModel]) -> FactSchema:
    root = SchemaNode.model_validate(
        source.model_json_schema(mode="serialization", by_alias=True)
    )
    return FactSchema(root=root, leaves=tuple(_leaves(root, root, "", frozenset())))


def schema_rows(
    source: type[BaseModel], value: JsonValue, prefix: str = ""
) -> list[StatisticRowFact]:
    schema = fact_schema(source)
    return list(schema.rows(schema.root, value, prefix))


def model_rows(model: BaseModel, prefix: str = "") -> list[StatisticRowFact]:
    dumped = _JSON.validate_python(model.model_dump(mode="json", by_alias=True))
    return schema_rows(type(model), dumped, prefix)


__all__ = [
    "FactSchema",
    "LeafKind",
    "NoDisplayFormError",
    "SchemaNode",
    "fact_schema",
    "model_rows",
    "schema_rows",
]
