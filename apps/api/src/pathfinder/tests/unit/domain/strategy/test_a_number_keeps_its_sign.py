from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue, ParamValue, from_wire

from pathfinder.domain.strategy.value_source import value_source


def _source(value: ParamValue, said: str) -> str:
    return value_source(
        value,
        placeholder=False,
        unset=False,
        request_texts=[said],
        display_name="Fitness score",
    )


@pytest.mark.parametrize(
    ("number", "said", "source"),
    [
        (-1.0, "genes with a fitness below -1", "stated"),
        (1.0, "genes with a fitness below -1", "chosen"),
        (-2.0, "-2 or lower", "stated"),
        (2.0, "a fitness score at most -2", "chosen"),
        (100.0, "the top ranked genes, ranks 1-100", "stated"),
        (-100.0, "the top ranked genes, ranks 1-100", "chosen"),
        (20.0, "fitness between 10 - 20", "stated"),
        (-20.0, "fitness between 10 - 20", "chosen"),
        (-2.0, "genes expressed in T-2 cells", "chosen"),
    ],
)
def test_a_number_keeps_the_sign_the_researcher_wrote(
    number: float, said: str, source: str
) -> None:
    assert _source(NumberValue(value=number), said) == source


def test_a_negative_range_bound_is_stated_only_with_its_minus() -> None:
    negative = from_wire("number-range", '{"min": -2, "max": 3}')

    assert (
        _source(negative, "a fitness score between -2 and 3"),
        _source(negative, "a fitness score between 2 and 3"),
    ) == ("stated", "chosen")
