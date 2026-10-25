"""A computed comparison names the parts of its group count a reply places:
the one-sided split, the residual groups and a species that leads a set."""

from __future__ import annotations

from datetime import date

from pydantic import TypeAdapter
from veupathdb.domain.parameters import InputDatasetValue
from veupathdb_mcp.catalog import PhyleticPattern
from veupathdb_mcp.wdk import ComputedComparisonResult, ComputedSet

from pathfinder.domain.strategy.computed_groups import SetFacts
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.tests._support.computed_comparison import COMPARISON, held_comparison

_PATTERN: PhyleticPattern = TypeAdapter(PhyleticPattern).validate_python(
    {
        "kind": "compare",
        "left": {"kind": "codes", "codes": ["aaaa"]},
        "right": {"kind": "codes", "codes": ["bbbb"]},
        "reading": "averages",
        "condition": "more_than",
    }
)


def _set(*genomes: int) -> ComputedSet:
    return ComputedSet.model_validate(
        {
            "side": "left",
            "genomes": sum(genomes),
            "species": [
                {"species": f"species {index}", "genomes": count}
                for index, count in enumerate(genomes)
            ],
            "groups": 1,
            "proteins": 1,
        }
    )


def _split(**counts: int) -> list[str]:
    answer = ComputedComparisonResult.model_validate(
        {**COMPARISON.model_dump(by_alias=True), **counts}
    )
    held = held_comparison(_PATTERN, date(2026, 10, 25)).model_copy(
        update={"answer": answer}
    )
    return list(held.facts().breakdown())


def test_a_species_past_the_share_leads_its_set() -> None:
    assert [
        SetFacts.of(_set(*g)).leading_species_leads for g in ((20, 7, 4), (1,))
    ] == [
        True,
        True,
    ]


def test_a_tie_or_a_small_share_leads_nothing() -> None:
    assert [
        SetFacts.of(_set(*g)).leading_species_leads for g in ((2, 2), (1, 1, 1, 1, 1))
    ] == [False, False]


def test_one_sided_groups_name_the_split_and_the_residual() -> None:
    assert _split() == [
        "bothHeld",
        "leftOnly",
        "residualGroups",
        "left.leadingSpecies",
        "left.leadingSpeciesShare",
        "right.leadingSpecies",
        "right.leadingSpeciesShare",
    ]


def test_groups_both_sets_hold_name_only_the_leading_species() -> None:
    assert _split(bothHeld=3, leftOnly=0, residualGroups=0) == [
        "left.leadingSpecies",
        "left.leadingSpeciesShare",
        "right.leadingSpecies",
        "right.leadingSpeciesShare",
    ]


def test_the_root_count_places_the_groups_of_the_root_step() -> None:
    held = held_comparison(_PATTERN, date(2026, 10, 25)).model_copy(
        update={"dataset_id": "7"}
    )
    spec = OperationalSpec(
        criteria=[
            Criterion(
                id="c1",
                text="the computed groups",
                resolved_params={
                    "group_names": BoundValue(
                        value=InputDatasetValue(dataset_id="7"), source="chosen"
                    )
                },
            )
        ]
    )

    assert [
        len(held.placed(spec, root).unplaced({"[root]"})) for root in ("c1", "c2")
    ] == [7, 0]
