"""Each set a phyletic pattern names carries the genome count the site's taxonomy
gives its codes, and a genome count no group can reach is named with both counts."""

from __future__ import annotations

from pathfinder.domain.strategy.pattern_sets import (
    CountBeyondSet,
    SetSize,
    counts_beyond_their_sets,
    set_sizes,
)
from pathfinder.tests._support.synthetic_taxonomy import pattern, synthetic_tree

_ONLY_IN_FERNS = pattern(
    {
        "kind": "all_of",
        "terms": [
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
                "right": {"kind": "codes", "codes": ["msa", "lna"]},
                "reading": "averages",
                "condition": "more_than",
            },
        ],
    }
)


def _count(of: object, condition: str, value: int) -> object:
    return {
        "kind": "count",
        "of": of,
        "measure": "genomes",
        "condition": condition,
        "value": value,
    }


def test_each_set_carries_the_genomes_its_codes_cover() -> None:
    assert set_sizes(_ONLY_IN_FERNS, synthetic_tree()) == (
        SetSize(kind="codes", codes=("FERN",), genomes=3),
        SetSize(kind="all_except", codes=("FERN",), genomes=3),
        SetSize(kind="codes", codes=("msa", "lna"), genomes=2),
    )


def test_a_count_past_the_genomes_of_its_set_is_named_with_both_counts() -> None:
    beyond = counts_beyond_their_sets(
        pattern(_count({"kind": "codes", "codes": ["MOSS"]}, "at_least", 3)),
        synthetic_tree(),
    )

    assert beyond == [
        CountBeyondSet(condition="at_least", value=3, named="MOSS", genomes=2)
    ]
    assert beyond[0].sentence == (
        "at least 3 genomes of MOSS asks for more genomes than it holds: its codes "
        "cover 2 genomes on the site's taxonomy. Read each set's genome count from "
        "`sets`, or state the bound as a share."
    )


def test_more_than_every_genome_of_a_set_is_past_it() -> None:
    beyond = counts_beyond_their_sets(
        pattern(_count({"kind": "codes", "codes": ["MOSS"]}, "more_than", 2)),
        synthetic_tree(),
    )

    assert [b.genomes for b in beyond] == [2]


def test_a_count_within_its_set_is_not_named() -> None:
    held = pattern(_count({"kind": "codes", "codes": ["MOSS"]}, "exactly", 2))

    assert counts_beyond_their_sets(held, synthetic_tree()) == []


def test_each_genome_of_a_clade_holds_one_genome() -> None:
    beyond = counts_beyond_their_sets(
        pattern(_count({"kind": "each_genome_of", "codes": ["FERN"]}, "at_least", 2)),
        synthetic_tree(),
    )

    assert [(b.named, b.genomes) for b in beyond] == [("each genome of FERN", 1)]


def test_each_species_is_held_to_its_largest_species() -> None:
    within = pattern(
        _count({"kind": "each_species_of", "codes": ["FERN"]}, "at_least", 2)
    )
    past = pattern(
        _count({"kind": "each_species_of", "codes": ["FERN"]}, "at_least", 3)
    )

    assert counts_beyond_their_sets(within, synthetic_tree()) == []
    assert [b.genomes for b in counts_beyond_their_sets(past, synthetic_tree())] == [2]
