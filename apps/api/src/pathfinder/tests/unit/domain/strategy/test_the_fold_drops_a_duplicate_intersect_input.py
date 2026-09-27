"""An INTERSECT input identical to a sibling input returns the sibling's records,
so the structure fold drops it and records it as met by the sibling."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.spec_duplicates import (
    DeduplicatedStructure,
    fold_duplicate_inputs,
)
from pathfinder.tests.unit.domain.strategy._n1_tree import (
    blood_stage,
    drug_target,
    join,
    leaf,
    low_variation,
    no_human,
    three,
)
from pathfinder.tests.unit.domain.strategy._orthology import (
    kept_by_intersect,
    round_trip_spec,
    seed_node,
)

ORIGINAL = ("step_9ba9dec1", "step_3a4dba81", "step_0ae0f092")
SECOND = ("step_e83414b3", "step_7764f323", "step_9f2e2b90")


def _spec(root: StructureNode) -> OperationalSpec:
    """The request's three leaves twice over, with the same searches and values."""
    return OperationalSpec(
        criteria=[
            *(
                make(cid)
                for ids in (ORIGINAL, SECOND)
                for make, cid in zip(
                    (blood_stage, low_variation, no_human), ids, strict=True
                )
            ),
            blood_stage("c_blood_70", minimum="70"),
            drug_target().model_copy(update={"role": "filter"}),
        ],
        structure=SpecStructure(root=root),
    )


def _folded(
    root: StructureNode, *, live: tuple[str, ...] = ()
) -> DeduplicatedStructure:
    return fold_duplicate_inputs(
        _spec(root), SpecStructure(root=root), live_step_ids=live
    )


def _dropped(folded: DeduplicatedStructure) -> list[tuple[str, str, bool]]:
    return [(d.criterion_id, d.fate, d.met) for d in folded.dropped]


def test_a_leaf_identical_to_a_sibling_is_dropped_as_met() -> None:
    root = join(
        CombineOp.INTERSECT,
        leaf("step_9ba9dec1"),
        leaf("step_3a4dba81"),
        leaf("step_e83414b3"),
    )

    folded = _folded(root)

    assert folded.structure.root == join(
        CombineOp.INTERSECT, leaf("step_9ba9dec1"), leaf("step_3a4dba81")
    )
    assert _dropped(folded) == [
        (
            "step_e83414b3",
            (
                "step_e83414b3 ('P. falciparum 3D7 genes expressed in the blood "
                "stage') is dropped: it runs "
                "GenesByRNASeqpfal3D7_Newbold_ebi_rnaSeq_RSRCPercentile with the "
                "values step_9ba9dec1 runs beside it under INTERSECT, so "
                "step_9ba9dec1 meets it."
            ),
            True,
        )
    ]


def test_a_second_copy_of_the_intersected_subtree_is_dropped() -> None:
    root = join(
        CombineOp.INTERSECT,
        join(CombineOp.INTERSECT, three(*ORIGINAL), leaf("c_drug_target")),
        three(*SECOND),
    )

    folded = _folded(root)

    assert folded.structure.root == join(
        CombineOp.INTERSECT, three(*ORIGINAL), leaf("c_drug_target")
    )
    assert [d.criterion_id for d in folded.dropped] == list(SECOND)
    assert [d.sibling_id for d in folded.dropped] == list(ORIGINAL)


def test_an_identical_union_branch_is_dropped_whole() -> None:
    first = join(CombineOp.UNION, leaf(ORIGINAL[0]), leaf(ORIGINAL[1]))
    second = join(CombineOp.UNION, leaf(SECOND[0]), leaf(SECOND[1]))
    root = join(CombineOp.INTERSECT, first, leaf(ORIGINAL[2]), second)

    folded = _folded(root)

    assert folded.structure.root == join(CombineOp.INTERSECT, first, leaf(ORIGINAL[2]))
    assert [(d.criterion_id, d.sibling_id) for d in folded.dropped] == [
        (SECOND[0], ORIGINAL[0]),
        (SECOND[1], ORIGINAL[1]),
    ]


def test_the_live_step_is_kept_over_its_unbuilt_duplicate() -> None:
    root = join(
        CombineOp.INTERSECT,
        leaf("step_e83414b3"),
        leaf("step_3a4dba81"),
        leaf("step_9ba9dec1"),
    )

    folded = _folded(root, live=("step_9ba9dec1", "step_3a4dba81"))

    assert folded.structure.root == join(
        CombineOp.INTERSECT, leaf("step_3a4dba81"), leaf("step_9ba9dec1")
    )
    assert [(d.criterion_id, d.sibling_id) for d in folded.dropped] == [
        ("step_e83414b3", "step_9ba9dec1")
    ]


def test_a_leaf_that_differs_in_one_value_is_kept() -> None:
    root = join(CombineOp.INTERSECT, leaf("step_9ba9dec1"), leaf("c_blood_70"))

    folded = _folded(root)

    assert folded.structure.root == root
    assert _dropped(folded) == []


def test_a_minus_input_is_never_dropped() -> None:
    root = join(CombineOp.MINUS, leaf("step_9ba9dec1"), leaf("step_e83414b3"))

    folded = _folded(root)

    assert folded.structure.root == root
    assert _dropped(folded) == []


def test_the_orthology_round_trip_keeps_its_copy() -> None:
    spec = round_trip_spec(kept_by_intersect(seed_node()))
    assert spec.structure is not None

    folded = fold_duplicate_inputs(spec, spec.structure, live_step_ids=())

    assert folded.structure == spec.structure
    assert _dropped(folded) == []
