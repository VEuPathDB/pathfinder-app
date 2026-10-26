"""A step's rows: each value it binds as a researcher reads it, and the
expression it runs whole."""

from __future__ import annotations

from veupathdb.domain.parameters import PHYLETIC_EXPRESSION_PARAM, StringValue

from pathfinder.ai.lead.parameter_facts import step_parameters
from pathfinder.domain.strategy.expression_handles import expression_handle
from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion

_EXPRESSION = "APIC>=1T AND MAMM=0T"


def _criterion(value: str) -> Criterion:
    return Criterion(
        id="c_pattern",
        text="groups in apicomplexans and in no mammal",
        search_name="GroupsByPhyleticPattern",
        resolved_params={
            PHYLETIC_EXPRESSION_PARAM: BoundValue(
                value=StringValue(value=value), source="stated"
            ),
            "text_expression": BoundValue(
                value=StringValue(value="kinase"), source="stated"
            ),
        },
        param_display_names={
            PHYLETIC_EXPRESSION_PARAM: "Expression",
            "text_expression": "Text term",
        },
    )


def test_the_expression_row_carries_the_expression_and_no_other_row_does() -> None:
    rows = step_parameters(_criterion(_EXPRESSION), "group", [])

    assert [(row.display_name, row.expression) for row in rows] == [
        ("Expression", _EXPRESSION),
        ("Text term", ""),
    ]


def test_a_handle_the_step_holds_is_no_expression_to_show() -> None:
    [row, _] = step_parameters(_criterion(expression_handle(_EXPRESSION)), "group", [])

    assert row.expression == ""
