"""A range value reads as its bounds: one number when they are equal, else the span."""

from __future__ import annotations

from typing import Literal

import pytest
from veupathdb.domain.parameters import from_wire

from pathfinder.domain.reply_references import render_reply
from pathfinder.domain.strategy.value_binding import plain_value
from pathfinder.domain.turn_facts import ParameterFact, StepFact, TurnFacts


@pytest.mark.parametrize(
    ("kind", "wire", "shown"),
    [
        ("number-range", '{"min": 1, "max": 1}', "1"),
        ("number-range", '{"min": 1, "max": 5}', "1 to 5"),
        ("number-range", '{"min": 0.5, "max": 2.25}', "0.5 to 2.25"),
        ("number-range", '{"min": 3}', "at least 3"),
        ("number-range", '{"max": 3}', "at most 3"),
        (
            "date-range",
            '{"min": "2020-01-01", "max": "2021-06-30"}',
            "2020-01-01 to 2021-06-30",
        ),
    ],
)
def test_a_range_reads_as_its_bounds(
    kind: Literal["number-range", "date-range"], wire: str, shown: str
) -> None:
    assert plain_value(from_wire(kind, wire)) == shown


def test_a_singleton_range_renders_in_its_clause_as_one_number() -> None:
    value = plain_value(from_wire("number-range", '{"min": 1, "max": 1}'))
    facts = TurnFacts(
        steps=[
            StepFact(
                step_id="step_ortho",
                display_name="Orthology phylogenetic profile",
                count=412,
                parameters=[
                    ParameterFact(
                        name="all_count",
                        display_name="Number of genes in each organism",
                        value=value,
                        source="stated",
                    )
                ],
            )
        ]
    )
    prose = (
        "The profile keeps genes with exactly [value:step_ortho.all_count] copy in "
        "each organism."
    )

    assert render_reply(prose, facts) == (
        "The profile keeps genes with exactly 1 copy in each organism."
    )
