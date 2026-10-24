from __future__ import annotations

import pytest
from pydantic import TypeAdapter
from veupathdb.domain.parameters import NumberValue, StringValue
from veupathdb_mcp.catalog import PhyleticPattern

from pathfinder.domain.strategy.expression_handles import (
    BuiltPattern,
    UnknownExpressionError,
    expression_handle,
    held_expressions,
    resolved_params,
    shown_parameters,
    shown_params,
    shown_wire,
)
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests._support.bound_values import bound

_EXPRESSION = " OR ".join(f"pfal={k} AND tgon>={k + 1}" for k in range(400))
_HELD = "APIC>=1T AND MAMM=0T"
_ADAPTER: TypeAdapter[PhyleticPattern] = TypeAdapter(PhyleticPattern)
_PATTERN = _ADAPTER.validate_python(
    {"kind": "count", "of": {"kind": "codes", "codes": ["APIC"]}, "condition": "absent"}
)


def _spec() -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            Criterion(
                id="c_groups",
                text="groups",
                search_name="GroupsByPhyleticPattern",
                resolved_params=bound(
                    {"phyletic_expression": StringValue(value=_HELD)}
                ),
            )
        ]
    )


def test_a_handle_names_its_expression_by_content() -> None:
    handle = expression_handle(_EXPRESSION)

    assert (handle.startswith("expr:"), len(handle), handle) == (
        True,
        17,
        expression_handle(str(_EXPRESSION)),
    )
    assert expression_handle(_HELD) != handle


def test_an_expression_is_shown_by_its_handle_and_any_other_value_as_written() -> None:
    shown = shown_params(
        {
            "phyletic_expression": StringValue(value=_EXPRESSION),
            "min_count": NumberValue(value=2),
        }
    )

    assert shown == {
        "phyletic_expression": expression_handle(_EXPRESSION),
        "min_count": "2",
    }
    assert shown_wire("phyletic_expression", _HELD) == expression_handle(_HELD)
    assert shown_parameters({"phyletic_expression": StringValue(value=_HELD)}) == {
        "phyletic_expression": StringValue(value=expression_handle(_HELD))
    }


def test_a_handle_resolves_to_a_built_or_a_bound_expression() -> None:
    held = held_expressions(
        {
            expression_handle(_EXPRESSION): BuiltPattern(
                expression=_EXPRESSION, pattern=_PATTERN, reading="absent from APIC"
            )
        },
        _spec(),
    )

    assert resolved_params(
        {"phyletic_expression": expression_handle(_HELD), "min_count": "2"}, held
    ) == {"phyletic_expression": _HELD, "min_count": "2"}
    assert resolved_params(
        {"phyletic_expression": expression_handle(_EXPRESSION)}, held
    ) == {"phyletic_expression": _EXPRESSION}


def test_a_typed_expression_resolves_to_itself() -> None:
    assert resolved_params({"phyletic_expression": _HELD}, {}) == {
        "phyletic_expression": _HELD
    }


def test_an_unknown_handle_is_refused_by_name() -> None:
    with pytest.raises(UnknownExpressionError) as refused:
        resolved_params({"phyletic_expression": "expr:000000000000"}, {})

    assert refused.value.handle == "expr:000000000000"
