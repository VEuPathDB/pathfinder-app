"""Free words on a dimension of one value never state a requirement, so the stated
value stays until a structured pick replaces it."""

from __future__ import annotations

import pytest

from strategist.ai.lead.answer_requirements import answer_requirement
from strategist.domain.strategy.constraints import ConstraintKind

_SINGLE_VALUED = [
    ConstraintKind.PERCENTILE,
    ConstraintKind.FOLD_CHANGE,
    ConstraintKind.STATISTICAL_THRESHOLD,
    ConstraintKind.DATA_TYPE,
    ConstraintKind.ORGANISM,
    ConstraintKind.RECORD_TYPE,
    ConstraintKind.COMPARATOR,
]
_WORDS = [
    "proceed with defaults",
    "p-value below 1e-5",
    "above the 90th percentile",
    "go with option 2",
    "Plasmodium falciparum 7G8",
]


@pytest.mark.parametrize("dimension", _SINGLE_VALUED)
@pytest.mark.parametrize("words", _WORDS)
def test_free_words_state_no_requirement(dimension: ConstraintKind, words: str) -> None:
    stated = answer_requirement(
        "Which value should replace this?", [], words, dimension
    )

    assert [stated] == [None]


def test_free_words_on_a_dimension_of_many_values_are_a_requirement() -> None:
    stated = answer_requirement(
        "What else should the genes have?", [], "a GPI anchor", ConstraintKind.PROPERTY
    )

    assert stated is not None
    assert (stated.kind, stated.requested_value) == (
        ConstraintKind.PROPERTY,
        "a GPI anchor",
    )
