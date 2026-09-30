"""An edit that narrows or widens the result keeps the organism its records
belong to; a one-way orthology transform under such an edit is refused."""

from __future__ import annotations

import pytest

from pathfinder.domain.caveats import EditDirection
from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.orthology import organism_move_refusal
from pathfinder.tests.unit.domain.strategy._orthology import (
    SOURCE,
    TARGET,
    leg,
    round_trip_spec,
    seed_criteria,
    seed_node,
)

_TRANSFORM = "c_syntenic_vivax_p01"


def _held() -> OperationalSpec:
    return OperationalSpec(
        goal="signal peptide and 2 to 99 transmembrane domains",
        criteria=seed_criteria(),
        structure=SpecStructure(root=seed_node()),
    )


def _one_way() -> OperationalSpec:
    return OperationalSpec(
        goal="keep only those with syntenic orthologs in Plasmodium vivax P01",
        criteria=[*seed_criteria(), leg(_TRANSFORM, TARGET, "yes")],
        structure=SpecStructure(
            root=StructureNode(
                kind="transform", criterion_id=_TRANSFORM, inputs=[seed_node()]
            )
        ),
    )


@pytest.mark.parametrize("direction", ["tighten", "loosen"])
def test_a_one_way_transform_under_a_narrowing_or_widening_edit_is_refused(
    direction: EditDirection,
) -> None:
    refusal = organism_move_refusal(direction, before=_held(), after=_one_way())

    assert refusal is not None
    assert f"answer genes of {TARGET}" in refusal
    assert f"the strategy answers genes of {SOURCE}" in refusal
    assert '"kind": "combine", "operator": "INTERSECT"' in refusal
    assert '"kind": "copy"' in refusal


def test_an_edit_that_asks_for_another_organism_or_keeps_it_is_not_refused() -> None:
    unmarked = [c.model_copy(update={"organism_param": None}) for c in seed_criteria()]
    held = _held().model_copy(update={"criteria": unmarked})
    edited = _one_way().model_copy(
        update={"criteria": [*unmarked, leg(_TRANSFORM, TARGET, "yes")]}
    )

    assert [
        organism_move_refusal("other", before=_held(), after=_one_way()),
        organism_move_refusal("tighten", before=_held(), after=round_trip_spec()),
        organism_move_refusal("tighten", before=held, after=edited),
    ] == [None, None, None]
