"""A requirement's clause is stated by a bound phyletic pattern when a term the
pattern must meet selects the same groups on the site's taxonomy."""

from __future__ import annotations

import pytest

from pathfinder.domain.strategy.pattern_clauses import states_clause
from pathfinder.tests._support.synthetic_taxonomy import pattern, synthetic_tree

_TERMS: list[object] = [
    {
        "kind": "count",
        "of": {"kind": "codes", "codes": ["FERN"]},
        "measure": "genomes",
        "condition": "at_least",
        "value": 2,
    },
    {
        "kind": "count",
        "of": {"kind": "all_except", "codes": ["FERN"]},
        "condition": "absent",
    },
    {
        "kind": "compare",
        "left": {"kind": "codes", "codes": ["FERN"]},
        "right": {"kind": "codes", "codes": ["MOSS"]},
        "reading": "averages",
        "condition": "more_than",
    },
]
_FERNS_ONLY = pattern({"kind": "all_of", "terms": _TERMS})


def _count(of: object, measure: str, condition: str, value: float) -> object:
    return {
        "kind": "count",
        "of": of,
        "measure": measure,
        "condition": condition,
        "value": value,
    }


_FERN = {"kind": "codes", "codes": ["FERN"]}
_NOT_FERN = {"kind": "codes", "codes": ["MOSS", "lna"]}


@pytest.mark.parametrize(
    "clause",
    [
        {
            "kind": "count",
            "of": {"kind": "all_except", "codes": ["FERN"]},
            "condition": "absent",
        },
        _count(_NOT_FERN, "genomes", "at_most", 0),
        _count(_NOT_FERN, "proteins", "fewer_than", 1),
        _count(_FERN, "share", "at_least", 50),
        _count(
            {"kind": "codes", "codes": ["fna", "fnb", "fnc"]}, "genomes", "more_than", 1
        ),
        {
            "kind": "compare",
            "left": {"kind": "codes", "codes": ["fna", "fnb", "fnc"]},
            "right": {"kind": "codes", "codes": ["msa", "msb"]},
            "reading": "averages",
            "condition": "more_than",
        },
    ],
)
def test_a_clause_the_pattern_must_meet_is_stated(clause: object) -> None:
    assert states_clause(_FERNS_ONLY, pattern(clause), synthetic_tree())


@pytest.mark.parametrize(
    "clause",
    [
        _count(_FERN, "genomes", "at_least", 3),
        _count(_FERN, "share", "at_least", 90),
        _count({"kind": "codes", "codes": ["MOSS"]}, "genomes", "at_most", 0),
        {
            "kind": "compare",
            "left": _FERN,
            "right": {"kind": "codes", "codes": ["MOSS"]},
            "reading": "totals",
            "condition": "more_than",
        },
        _count({"kind": "codes", "codes": ["XXXX"]}, "genomes", "at_most", 0),
    ],
)
def test_a_clause_the_pattern_does_not_force_is_not_stated(clause: object) -> None:
    assert not states_clause(_FERNS_ONLY, pattern(clause), synthetic_tree())


def test_a_term_of_an_alternative_is_not_stated() -> None:
    either = pattern({"kind": "any_of", "terms": _TERMS})

    absent = pattern(_count(_NOT_FERN, "genomes", "at_most", 0))

    assert not states_clause(either, absent, synthetic_tree())


def test_none_of_a_presence_states_the_absence() -> None:
    held = pattern(
        {"kind": "none_of", "terms": [_count(_NOT_FERN, "genomes", "at_least", 1)]}
    )
    absent = pattern({"kind": "count", "of": _NOT_FERN, "condition": "absent"})

    assert states_clause(held, absent, synthetic_tree())


def test_a_clause_of_several_terms_is_stated_when_each_is() -> None:
    both = pattern(
        {
            "kind": "all_of",
            "terms": [
                _count(_FERN, "genomes", "at_least", 2),
                _count(_NOT_FERN, "genomes", "exactly", 0),
            ],
        }
    )

    assert states_clause(_FERNS_ONLY, both, synthetic_tree())
