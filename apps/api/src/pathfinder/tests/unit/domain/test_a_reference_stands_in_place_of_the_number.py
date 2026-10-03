"""A reference stands in place of the number and carries its noun: a number word
in the clause of a count or value reference, and a count noun just after a count
reference, are faults. A digit of a record's product names the record reference."""

from __future__ import annotations

import pytest

from pathfinder.domain.comparison_facts import ComparedVariant, ComparisonFact
from pathfinder.domain.reply_references import ProseFault, prose_faults
from pathfinder.domain.turn_facts import ParameterFact, SourceFact, StepFact, TurnFacts

_PLASMO = TurnFacts(
    steps=[
        StepFact(
            step_id="step_5c5aea5d",
            display_name="Transmembrane Domain Count",
            count=4210,
            parameters=[
                ParameterFact(
                    name="min_tm", display_name="Minimum", value="1", source="stated"
                )
            ],
        ),
        StepFact(
            step_id="step_9c74f378",
            display_name="RNA-Seq Fold Change",
            count=603,
            parameters=[
                ParameterFact(
                    name="fold_change",
                    display_name="Fold change",
                    value="2",
                    source="default",
                )
            ],
        ),
    ],
    root_count=603,
)
_TOXO = TurnFacts(
    steps=[StepFact(step_id="step_30da93c3", display_name="Pfam Domain", count=85)],
    root_count=85,
    comparisons=[
        ComparisonFact(
            variants=[
                ComparedVariant(
                    label="ME49", gene_count=87, unique_count=2, result_count=87
                ),
                ComparedVariant(label="RH-88", gene_count=85, unique_count=0),
            ]
        )
    ],
)
_RECORD = "https://microsporidiadb.org/micro/app/record/gene/VICG_00034"
_MICRO = TurnFacts(
    sources=[
        SourceFact(
            url=_RECORD,
            record_id="VICG_00034",
            product="Dynein heavy chain, N-terminal region 2",
        )
    ],
)


def test_a_number_word_beside_a_value_reference_is_refused() -> None:
    prose = (
        "It keeps genes with at least one predicted transmembrane domain "
        "[value:step_5c5aea5d.min_tm]."
    )

    assert prose_faults(prose, _PLASMO) == [
        ProseFault(
            token=(
                "It keeps genes with at least one predicted transmembrane domain "
                "[value:step_5c5aea5d.min_tm]"
            ),
            kind="number_word",
            references=("[value:step_5c5aea5d.min_tm]",),
        )
    ]


def test_a_fold_word_beside_a_value_reference_is_refused() -> None:
    prose = (
        "It uses the two-fold expression threshold [value:step_9c74f378.fold_change]."
    )

    assert [(f.kind, f.references) for f in prose_faults(prose, _PLASMO)] == [
        ("number_word", ("[value:step_9c74f378.fold_change]",))
    ]


@pytest.mark.parametrize(
    "prose",
    [
        "Two steps keep [count:step_5c5aea5d].",
        "The result [root] is twice smaller.",
        "It removed [diff:step_5c5aea5d,root] in three passes.",
        "The subset [count:step_5c5aea5d] is about a third of [root].",
        "Roughly half of [root] carry it, [count:step_5c5aea5d].",
    ],
)
def test_a_number_word_in_the_clause_of_a_count_reference_is_refused(
    prose: str,
) -> None:
    assert [f.kind for f in prose_faults(prose, _PLASMO)] == ["number_word"]


@pytest.mark.parametrize(
    "prose",
    [
        "The strategy has two steps; the result is [root].",
        "The intersect keeps [count:step_5c5aea5d] in both searches.",
    ],
)
def test_a_number_word_in_another_clause_or_both_stands(prose: str) -> None:
    assert prose_faults(prose, _PLASMO) == []


def test_a_count_noun_after_a_difference_is_refused() -> None:
    prose = "ME49 has [diff:compare:ME49,compare:RH-88] more matching genes."

    assert prose_faults(prose, _TOXO) == [
        ProseFault(
            token="[diff:compare:ME49,compare:RH-88] more matching genes",
            kind="noun_after_count",
            references=("[diff:compare:ME49,compare:RH-88]",),
        )
    ]


@pytest.mark.parametrize(
    "prose",
    [
        "It returns [count:step_30da93c3] genes.",
        "On ME49 it returns [compare:ME49:result] genes.",
        "Before the edit it held [root] records.",
        "It adds [count:step_30da93c3] additional genes.",
    ],
)
def test_a_count_noun_after_a_count_reference_is_refused(prose: str) -> None:
    assert [f.kind for f in prose_faults(prose, _TOXO)] == ["noun_after_count"]


def test_the_record_noun_of_the_strategy_is_a_count_noun() -> None:
    facts = TurnFacts(record_noun="popset isolate sequence", root_count=12)

    assert [f.kind for f in prose_faults("It holds [root] sequences.", facts)] == [
        "noun_after_count"
    ]


@pytest.mark.parametrize(
    "prose",
    [
        "It returns [count:step_30da93c3], the overall result.",
        "ME49 has [diff:compare:ME49,compare:RH-88] more.",
        "The result [root] holds genes with a signal peptide.",
        "It returns [count:step_30da93c3] of which genes stay.",
        "The PfEMP1 genes of 3D7 are kept, and it returns [root].",
    ],
)
def test_a_reference_that_carries_its_own_number_and_noun_stands(prose: str) -> None:
    assert prose_faults(prose, _TOXO) == []


def test_a_digit_of_a_record_s_product_names_the_record_reference() -> None:
    prose = "[record:VICG_00034] - Dynein heavy chain, N-terminal region 2."

    assert prose_faults(prose, _MICRO) == [
        ProseFault(
            token="2",
            kind="product_text",
            references=("[record:VICG_00034]",),
            record_id="VICG_00034",
        )
    ]


def test_a_digit_in_no_product_is_a_number() -> None:
    assert prose_faults("[record:VICG_00034] is one of 3 hits.", _MICRO) == [
        ProseFault(token="3", kind="number")
    ]
