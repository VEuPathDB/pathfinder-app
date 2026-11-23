"""The key a refused tool call is charged under, read from the tool's own schema."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from pydantic.alias_generators import to_snake
from pydantic_ai.tools import ToolDefinition
from pydantic_core import ErrorDetails, to_jsonable_python

from strategist.domain.refusal import Check, Problem, Problems, RefusalKey

_PRIMARY = ("criterion_id", "step_id", "label")
_TARGETS = frozenset({"label", "column", "record_type"})


def _identifies(name: str) -> bool:
    return name.endswith(("_id", "search_name")) or name in _TARGETS


class _Field(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    ref: str = Field(default="", alias="$ref")
    any_of: list[_Field] = Field(default_factory=list, alias="anyOf")

    def model(self) -> str:
        refs = [self.ref, *(choice.model() for choice in self.any_of)]
        return next((ref.rsplit("/", 1)[-1] for ref in refs if ref), "")


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")

    properties: dict[str, _Field] = Field(default_factory=dict)


class _Arguments(_Model):
    defs: dict[str, _Model] = Field(default_factory=dict, alias="$defs")


def _targets(
    model: _Model, defs: Mapping[str, _Model], args: Mapping[str, Any], *, nested: bool
) -> list[tuple[str, str]]:
    given = {to_snake(name): value for name, value in args.items()}
    found: list[tuple[str, str]] = []
    for name, declared in model.properties.items():
        field = to_snake(name)
        match given.get(field):
            case bool() | None:
                continue
            case str() | int() as value if _identifies(field) and value != "":
                found.append((field, str(value)))
            case Mapping() as inner if not nested and declared.model() in defs:
                found += _targets(defs[declared.model()], defs, inner, nested=True)
            case _:
                continue
    return found


def call_key(tool: ToolDefinition, args: Mapping[str, Any]) -> RefusalKey:
    schema = _Arguments.model_validate(tool.parameters_json_schema)
    given = to_jsonable_python(args, by_alias=True)
    found = _targets(schema, schema.defs, given, nested=False)
    searches = [pair for pair in found if pair[0].endswith("search_name")]
    primary = next((pair for pair in found if pair[0] in _PRIMARY), None)
    named = [primary[1]] if primary else []
    rest = [
        f"{n}={v}" for n, v in found if (n, v) not in searches and (n, v) != primary
    ]
    return RefusalKey(
        check=tool.name,
        criterion="; ".join([*named, *rest]),
        search=searches[0][1] if searches else "",
    )


_SENT = TypeAdapter(dict[str, Any])


def sent_arguments(args: str | dict[str, Any]) -> dict[str, Any]:
    match args:
        case str():
            try:
                return _SENT.validate_json(args or "{}")
            except ValidationError:
                return {}
        case _:
            return args


def _field_problem(tool: str, error: ErrorDetails, near: RefusalKey) -> Problem:
    where = ".".join(str(part) for part in error["loc"])
    said = error["msg"].removeprefix("Value error, ").rstrip(".")
    match error["input"]:
        case str() | int() | float() as value:
            said = f"{said} (got {value!r})"
        case _:
            pass
    return Problem(
        key=RefusalKey(
            check=Check.ARGUMENTS,
            criterion=near.criterion,
            search=near.search,
            parameter=f"{tool}.{where}" if where else tool,
        ),
        sentence=f"{where}: {said}." if where else f"{said}.",
    )


def argument_problems(
    tool: ToolDefinition, sent: dict[str, Any], error: ValidationError
) -> Problems:
    found = error.errors(include_url=False, include_context=False)
    invalid = {str(e["loc"][0]) for e in found if e["loc"]}
    near = call_key(tool, {k: v for k, v in sent.items() if k not in invalid})
    return Problems(found=tuple(_field_problem(tool.name, e, near) for e in found))


__all__ = ["argument_problems", "call_key", "sent_arguments"]
