"""Every parameter value reads as words: a range as its bounds, a filter as its clauses, never as its JSON wire text."""

from __future__ import annotations

from typing import Literal, get_args

import pytest
from veupathdb.domain.parameters import ParamKind, from_wire

from pathfinder.domain.strategy.value_binding import plain_value
from pathfinder.domain.turn_facts import ParameterFact, StepFact, TurnFacts

_SHOWN: dict[str, tuple[str, str]] = {
    "string": ("kinase", "kinase"),
    "number": ("5", "5"),
    "number-range": ('{"min": 1, "max": 5}', "1 to 5"),
    "date": ("2020-01-01", "2020-01-01"),
    "date-range": (
        '{"min": "2020-01-01", "max": "2021-06-30"}',
        "2020-01-01 to 2021-06-30",
    ),
    "timestamp": ("1700000000", "1700000000"),
    "single-pick-vocabulary": ("Pf3D7", "Pf3D7"),
    "multi-pick-vocabulary": ('["Pf3D7", "PvP01"]', "Pf3D7, PvP01"),
    "filter": (
        (
            '{"filters": [{"field": "sex", "value": ["female"]}, {"field": "maf", '
            '"type": "number", "isRange": true, "value": {"max": 0.05}}]}'
        ),
        "sex: female; maf: at most 0.05",
    ),
    "input-dataset": ("123456", "123456"),
    "input-step": ("227288240", "227288240"),
}


def test_every_parameter_kind_reads_as_words() -> None:
    kinds: tuple[ParamKind, ...] = get_args(ParamKind)

    assert set(kinds) == set(_SHOWN)
    assert {kind: plain_value(from_wire(kind, _SHOWN[kind][0])) for kind in kinds} == {
        kind: shown for kind, (_, shown) in _SHOWN.items()
    }


@pytest.mark.parametrize(
    ("kind", "wire", "shown"),
    [
        ("number-range", '{"min": 1, "max": 1}', "1"),
        ("number-range", '{"min": 0.5, "max": 2.25}', "0.5 to 2.25"),
        ("number-range", '{"min": 3}', "at least 3"),
        ("number-range", '{"max": 3}', "at most 3"),
        ("filter", '{"filters": []}', "no filter"),
        (
            "filter",
            (
                '{"filters": [{"field": "sex", "value": ["female", "male"], '
                '"includeUnknown": true}]}'
            ),
            "sex: female, male or unknown",
        ),
        (
            "filter",
            (
                '{"filters": [{"field": "variants_per_kb", "type": "number", '
                '"isRange": true, "value": {"min": 0, "max": 0}}]}'
            ),
            "variants_per_kb: 0",
        ),
    ],
)
def test_a_range_and_a_filter_read_as_their_bounds(
    kind: Literal["number-range", "filter"], wire: str, shown: str
) -> None:
    assert plain_value(from_wire(kind, wire)) == shown


def test_the_recorded_singleton_row_shows_one_number() -> None:
    facts = TurnFacts(
        record_noun="group",
        steps=[
            StepFact(
                step_id="step_88b8197d",
                display_name="Number of Sequences",
                count=523795,
                record_noun="group",
                parameters=[
                    ParameterFact(
                        name="all_count",
                        display_name="Number of All Proteins",
                        value=plain_value(
                            from_wire("number-range", '{"min": 1.0, "max": 1.0}')
                        ),
                        source="chosen",
                    )
                ],
            )
        ],
    )

    assert [line for line in facts.lines() if "Proteins" in line] == [
        "Number of All Proteins: 1"
    ]
