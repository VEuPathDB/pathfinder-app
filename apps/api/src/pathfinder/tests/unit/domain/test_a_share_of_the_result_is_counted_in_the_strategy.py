"""A variant counted in place shows its count inside the strategy beside its size
alone, and a reply that quotes only the size alone of a variant larger than the
result with it in place is refused."""

from __future__ import annotations

from pathfinder.ai.lead.contract_messages import unrendered_prose_message
from pathfinder.domain.comparison_facts import ComparedVariant, ComparisonFact
from pathfinder.domain.reply_references import ProseFault, prose_faults
from pathfinder.domain.turn_facts import TurnFacts

_SPLIT = TurnFacts(
    root_count=57,
    comparisons=[
        ComparisonFact(
            variants=[
                ComparedVariant(
                    label="North",
                    gene_count=6120,
                    unique_count=6120,
                    result_count=41,
                ),
                ComparedVariant(
                    label="South",
                    gene_count=12,
                    unique_count=12,
                    result_count=16,
                ),
            ]
        )
    ],
)


def test_a_variant_counted_in_place_shows_both_counts() -> None:
    assert _SPLIT.lines() == [
        "Result: 57 genes",
        "North: 6,120 genes alone; 41 genes in the strategy's result",
        "South: 12 genes alone; 16 genes in the strategy's result",
    ]


def test_a_variant_not_counted_in_place_shows_its_size() -> None:
    variant = ComparedVariant(label="East", gene_count=3, unique_count=3)

    assert variant.row("gene") == "East: 3 genes"


def test_a_size_alone_quoted_without_the_count_in_place_is_refused() -> None:
    prose = (
        "The result splits into [compare:North] from North and [compare:South:result]."
    )

    assert prose_faults(prose, _SPLIT) == [
        ProseFault(
            token="[compare:North]",
            kind="standalone_count",
            references=("[compare:North:result]",),
        )
    ]


def test_a_size_alone_beside_its_count_in_place_stands() -> None:
    prose = (
        "North alone holds [compare:North]; in the strategy it gives "
        "[compare:North:result] and South gives [compare:South:result]."
    )

    assert prose_faults(prose, _SPLIT) == []


def test_a_size_alone_no_larger_than_the_count_in_place_stands() -> None:
    prose = "South holds [compare:South]."

    assert prose_faults(prose, _SPLIT) == []


def test_the_refusal_names_the_count_in_the_strategy() -> None:
    fault = ProseFault(
        token="[compare:North]",
        kind="standalone_count",
        references=("[compare:North:result]",),
    )

    assert unrendered_prose_message([fault]).splitlines()[1] == (
        "- ``[compare:North]`` is that variant's size on its own, larger than the "
        "strategy's result with it in place, so it is no share of the result: "
        "write ``[compare:North:result]``, its count in the strategy."
    )
