from __future__ import annotations

from datetime import date

import pytest
from veupathdb.domain.parameters import InputDatasetValue, ParamValue, StringValue
from veupathdb_mcp.wdk import ComputedComparisonResult, ComputedSet

from pathfinder.domain.strategy.comparison_placement import placed_comparison
from pathfinder.domain.strategy.computed_groups import HeldComparison, SetFacts
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.tests._support.computed_comparison import (
    COMPARISON,
    PATTERN,
    held_comparison,
)

_DAY = date(2026, 10, 25)


def _set(side: str, *genomes: int) -> dict[str, object]:
    return {
        "side": side,
        "genomes": sum(genomes),
        "species": [
            {"species": f"species {index}", "genomes": count}
            for index, count in enumerate(genomes)
        ],
        "groups": 1,
        "proteins": 1,
    }


def _held(**counts: object) -> HeldComparison:
    answer = ComputedComparisonResult.model_validate(
        {**COMPARISON.model_dump(by_alias=True), **counts}
    )
    return held_comparison(PATTERN, _DAY).model_copy(update={"answer": answer})


def _spec(value: ParamValue) -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            Criterion(
                id="c1",
                text="the computed groups",
                resolved_params={
                    "group_names": BoundValue(value=value, source="chosen")
                },
            )
        ]
    )


@pytest.mark.parametrize(
    ("genomes", "leads"),
    [
        ((14, 7), True),
        ((20, 7, 4), True),
        ((13, 7), False),
        ((2, 2), False),
        ((5,), False),
    ],
)
def test_a_species_leads_with_twice_the_runner_up(
    genomes: tuple[int, ...], leads: bool
) -> None:
    held = ComputedSet.model_validate(_set("left", *genomes))

    assert SetFacts.of(held).leading_species_leads == leads


def test_the_leading_flag_is_no_row_of_the_card() -> None:
    names = [row.name for row in _held().fact().rows]

    assert [name for name in names if name.endswith("Leads")] == []


def test_one_sided_groups_name_the_split_and_the_residual() -> None:
    assert _held().facts().breakdown() == (
        ("bothHeld", "bothHeldShare"),
        ("leftOnly", "leftOnlyShare"),
        ("residualGroups", "residualGroupsShare"),
        ("right.leadingSpecies",),
        ("right.leadingSpeciesShare", "right.leadingSpeciesGenomes"),
    )


def test_groups_both_sets_hold_name_only_the_leading_species() -> None:
    held = _held(bothHeld=3, leftOnly=0, residualGroups=0)

    assert held.facts().breakdown() == (
        ("right.leadingSpecies",),
        ("right.leadingSpeciesShare", "right.leadingSpeciesGenomes"),
    )


def test_every_breakdown_path_is_a_row_of_the_fact() -> None:
    held = _held(
        bothHeld=1,
        leftOnly=1,
        rightOnly=1,
        sets=[_set("left", 4, 1), _set("right", 2, 1)],
    )
    paths = {path for need in held.facts().breakdown() for path in need}

    assert sorted(paths - {row.name for row in held.fact().rows}) == []
    assert len(paths) == 14


def test_the_root_count_places_the_groups_of_the_root_step() -> None:
    held = _held().model_copy(update={"dataset_id": "7"})
    spec = _spec(InputDatasetValue(dataset_id="7"))

    assert [
        len(placed_comparison(held, spec, root).unplaced("[root]"))
        for root in ("c1", "c2", None)
    ] == [5, 0, 0]


@pytest.mark.parametrize(
    ("dataset_id", "value"),
    [
        (None, StringValue(value="OG7_0000001")),
        ("7", InputDatasetValue(dataset_id="8")),
        ("7", StringValue(value="7")),
    ],
)
def test_a_comparison_binds_only_the_criterion_on_its_saved_list(
    dataset_id: str | None, value: ParamValue
) -> None:
    held = _held().model_copy(update={"dataset_id": dataset_id})

    assert held.bound_in(_spec(value)) == []
