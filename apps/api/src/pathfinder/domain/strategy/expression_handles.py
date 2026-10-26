from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping

from pydantic import ConfigDict
from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    ParamValue,
    PhyleticExpression,
    PhyleticTree,
    StringValue,
    to_wire,
)
from veupathdb.model import CamelModel
from veupathdb_mcp.catalog import PhyleticPattern

from pathfinder.domain.strategy.computed_groups import COMPARISON_PREFIX
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.value_binding import plain_value

READING_LIMIT = 2_000
_PREFIX = "expr:"
_DIGITS = 12
_HANDLE = re.compile(rf"{_PREFIX}[0-9a-f]{{{_DIGITS}}}")
_NAMED = re.compile(rf"(?:{_PREFIX}|{COMPARISON_PREFIX})[0-9a-f]{{{_DIGITS}}}")


class BuiltPattern(CamelModel):
    model_config = ConfigDict(frozen=True)

    expression: str
    pattern: PhyleticPattern
    reading: str


class UnknownExpressionError(ValueError):
    def __init__(self, handle: str) -> None:
        self.handle = handle
        super().__init__(handle)


def expression_handle(expression: str) -> str:
    digest = hashlib.sha256(expression.encode()).hexdigest()
    return f"{_PREFIX}{digest[:_DIGITS]}"


def is_handle(text: str) -> bool:
    return _HANDLE.fullmatch(text.strip()) is not None


def handles_in(text: str) -> set[str]:
    return set(_NAMED.findall(text))


def spec_handles(spec: OperationalSpec | None) -> set[str]:
    return set(_bound_expressions(spec))


def shown_wire(name: str, wire: str) -> str:
    if name == PHYLETIC_EXPRESSION_PARAM and wire and not is_handle(wire):
        return expression_handle(wire)
    return wire


def shown_value(name: str, value: ParamValue) -> str:
    return shown_wire(name, plain_value(value))


def shown_params(values: Mapping[str, ParamValue]) -> dict[str, str]:
    return {name: shown_wire(name, to_wire(value)) for name, value in values.items()}


def shown_parameters(values: Mapping[str, ParamValue]) -> dict[str, ParamValue]:
    return {
        name: StringValue(value=shown_wire(name, to_wire(value)))
        if name == PHYLETIC_EXPRESSION_PARAM
        else value
        for name, value in values.items()
    }


def _bound_texts(spec: OperationalSpec | None) -> list[tuple[str, str]]:
    bound = [] if spec is None else spec.criteria
    return [
        (criterion.id, text)
        for criterion in bound
        if (value := criterion.param_values.get(PHYLETIC_EXPRESSION_PARAM))
        and (text := to_wire(value))
    ]


def _bound_expressions(spec: OperationalSpec | None) -> dict[str, str]:
    return {expression_handle(text): text for _, text in _bound_texts(spec)}


def bound_patterns(
    built: Mapping[str, BuiltPattern], spec: OperationalSpec
) -> list[tuple[str, PhyleticPattern]]:
    return [
        (criterion_id, built[handle].pattern)
        for criterion_id, text in _bound_texts(spec)
        if (handle := expression_handle(text)) in built
    ]


def expression_reading(text: str, tree: PhyleticTree) -> str:
    expression = PhyleticExpression.parse(text)
    if len(text) <= READING_LIMIT:
        described = expression.describe(tree)
        if len(described) <= READING_LIMIT:
            return described
    root = expression.site_reading().root
    terms = root.operands("OR")
    joined = (
        f"{len(terms)} OR terms"
        if len(terms) > 1
        else f"{len(root.operands('AND'))} AND clauses"
    )
    return (
        f"names {len(expression.codes())} codes in {joined}, {len(text):,} characters"
    )


def held_expressions(
    built: Mapping[str, BuiltPattern], spec: OperationalSpec | None
) -> dict[str, str]:
    return {
        **_bound_expressions(spec),
        **{handle: held.expression for handle, held in built.items()},
    }


def held_readings(built: Mapping[str, BuiltPattern]) -> dict[str, str]:
    return {handle: held.reading for handle, held in built.items()}


def resolved_params(
    params: Mapping[str, str], held: Mapping[str, str]
) -> dict[str, str]:
    proposed = params.get(PHYLETIC_EXPRESSION_PARAM)
    if proposed is None or not is_handle(proposed):
        return dict(params)
    handle = proposed.strip()
    if handle not in held:
        raise UnknownExpressionError(handle)
    return {**params, PHYLETIC_EXPRESSION_PARAM: held[handle]}


__all__ = [
    "READING_LIMIT",
    "BuiltPattern",
    "UnknownExpressionError",
    "bound_patterns",
    "expression_handle",
    "expression_reading",
    "handles_in",
    "held_expressions",
    "held_readings",
    "is_handle",
    "resolved_params",
    "shown_parameters",
    "shown_params",
    "shown_value",
    "shown_wire",
    "spec_handles",
]
