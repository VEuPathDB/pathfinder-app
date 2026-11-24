from __future__ import annotations

import pytest

from strategist.ai.lead.answer_requirements import answer_requirement
from strategist.domain.strategy.constraints import (
    ConstraintKind,
    DataTypeValue,
    FoldChangeValue,
    PercentileValue,
    RequirementValue,
    SignificanceValue,
)

_SINGLE_VALUED = [
    ConstraintKind.PERCENTILE,
    ConstraintKind.FOLD_CHANGE,
    ConstraintKind.STATISTICAL_THRESHOLD,
    ConstraintKind.DATA_TYPE,
    ConstraintKind.ORGANISM,
    ConstraintKind.RECORD_TYPE,
    ConstraintKind.COMPARATOR,
]


@pytest.mark.parametrize("dimension", _SINGLE_VALUED)
def test_words_that_name_no_value_state_no_requirement(
    dimension: ConstraintKind,
) -> None:
    stated = answer_requirement(
        "Which value should replace this setting?",
        [],
        "proceed with defaults",
        dimension,
        ["Plasmodium falciparum 3D7"],
    )

    assert [stated] == [None]


@pytest.mark.parametrize(
    ("dimension", "words", "value"),
    [
        (
            ConstraintKind.PERCENTILE,
            "top 10 percent",
            PercentileValue(end="top", share=10),
        ),
        (
            ConstraintKind.PERCENTILE,
            "bottom 25%",
            PercentileValue(end="bottom", share=25),
        ),
        (ConstraintKind.FOLD_CHANGE, "2-fold", FoldChangeValue(cut=2)),
        (
            ConstraintKind.FOLD_CHANGE,
            "log2 fold change of 1.5",
            FoldChangeValue(cut=1.5, scale="log2"),
        ),
        (
            ConstraintKind.STATISTICAL_THRESHOLD,
            "p below 0.01",
            SignificanceValue(at_most=0.01),
        ),
        (ConstraintKind.DATA_TYPE, "use RNA-Seq", DataTypeValue(data="rna_seq")),
        (ConstraintKind.DATA_TYPE, "microarray", DataTypeValue(data="microarray")),
    ],
)
def test_words_that_name_a_value_state_it(
    dimension: ConstraintKind, words: str, value: RequirementValue
) -> None:
    stated = answer_requirement("Which value?", [], words, dimension, [])

    assert stated is not None
    assert (stated.requested_value, stated.value) == (words, value)
