"""The orthology round trip keeps the source organism only under an INTERSECT
with the source, over a copy of the source, with one synteny value on both legs."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, SinglePickValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    extract_output_organisms,
    walk,
)

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    StructureNode,
)
from pathfinder.domain.strategy.orthology import (
    OrganismChange,
    copy_refusal,
    organism_change,
    restate_copies,
    round_trip_refusal,
)
from pathfinder.domain.strategy.spec_tree import build_step_tree

from ._orthology import (
    ORTHOLOGS,
    SOURCE,
    TARGET,
    copy_of,
    round_trip_spec,
    seed_criteria,
    seed_node,
    trip,
)


def _kinds(node: StructureNode) -> list[str]:
    return [node.kind, *(kind for child in node.inputs for kind in _kinds(child))]


def test_the_round_trip_builds_the_seed_intersect_its_two_transforms() -> None:
    built = build_step_tree(restate_copies(round_trip_spec())).root

    assert built.operator is CombineOp.INTERSECT
    seed, back = built.primary_input, built.secondary_input
    assert seed is not None
    assert back is not None
    assert back.search_name == ORTHOLOGS
    there = back.primary_input
    assert there is not None
    assert there.search_name == ORTHOLOGS
    clone = there.primary_input
    assert clone is not None
    assert [n.search_name for n in walk(clone)] == [
        "GenesWithSignalPeptide",
        "GenesByTransmembraneDomains",
        COMBINE_SEARCH_NAME,
    ]
    assert [n.parameters for n in walk(clone)] == [n.parameters for n in walk(seed)]
    assert {n.id for n in walk(clone)}.isdisjoint({n.id for n in walk(seed)})


def test_the_double_transform_keeps_the_source_organism() -> None:
    built = build_step_tree(restate_copies(round_trip_spec())).root

    assert extract_output_organisms(built) == {SOURCE}
    assert built.secondary_input is not None
    there = built.secondary_input.primary_input
    assert there is not None
    assert extract_output_organisms(there) == {TARGET}


def test_a_restated_copy_is_criteria_of_its_own_and_no_copy_node() -> None:
    restated = restate_copies(round_trip_spec())

    assert restated.structure is not None
    assert "copy" not in _kinds(restated.structure.root)
    originals = {c.id for c in seed_criteria()}
    clones = [
        c for c in restated.criteria if c.id not in {*originals, "c_to", "c_back"}
    ]
    assert sorted(c.search_name for c in clones) == [
        "GenesByTransmembraneDomains",
        "GenesWithSignalPeptide",
    ]
    assert all(c.rationale is None for c in clones)
    assert len({c.id for c in restated.criteria}) == len(restated.criteria) == 6


def test_a_copy_of_an_unbound_criterion_stays_a_copy() -> None:
    open_seed = seed_criteria()
    open_seed[0] = open_seed[0].model_copy(
        update={
            "open_params": [
                OpenSlot(
                    criterion_id="c_signal",
                    param_name="signalp_version",
                    question="Which SignalP version?",
                )
            ]
        }
    )
    spec = round_trip_spec(seed=open_seed)

    restated = restate_copies(spec)

    assert restated == spec


def test_the_stated_round_trip_passes() -> None:
    spec = round_trip_spec()
    assert spec.structure is not None

    assert (
        copy_refusal(spec.structure.root),
        round_trip_refusal(spec),
        round_trip_refusal(restate_copies(spec)),
    ) == (None, None, None)


_KEEP_THE_SOURCE = (
    "c_back (Transform by Orthology) maps the genes of c_to back to Plasmodium "
    "falciparum 3D7. A round trip alone returns every source gene that is an "
    "ortholog or a paralog of a mapped gene, which holds genes the source never "
    'held. Keep the source genes: state {"kind": "combine", "operator": '
    '"INTERSECT", "inputs": [<the source subtree>, <the transform back>]}, and '
    'give the first transform {"kind": "copy", "inputs": [<the source '
    "subtree>]} as its input."
)


def test_a_round_trip_without_the_intersect_is_refused() -> None:
    spec = round_trip_spec(trip(seed_node()))

    assert round_trip_refusal(spec) == _KEEP_THE_SOURCE


def test_a_round_trip_over_a_subtree_the_intersect_does_not_hold_is_refused() -> None:
    root = StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[
            seed_node(),
            trip(copy_of(StructureNode(kind="leaf", criterion_id="c_signal"))),
        ],
    )

    assert round_trip_refusal(round_trip_spec(root)) == _KEEP_THE_SOURCE


def test_legs_with_different_synteny_values_are_refused() -> None:
    assert round_trip_refusal(round_trip_spec(back_syntenic="no")) == (
        "c_to and c_back are the two legs of one round trip, and isSyntenic "
        "differs: yes and no. Both legs carry the same values, except the "
        "organism each maps to."
    )


def test_only_a_round_trip_the_edit_touches_is_read() -> None:
    spec = round_trip_spec(trip(seed_node()))

    assert (
        round_trip_refusal(spec, touched={"c_signal"}),
        round_trip_refusal(spec, touched={"c_to"}),
    ) == (None, _KEEP_THE_SOURCE)


def test_a_criterion_named_twice_outside_a_copy_is_refused() -> None:
    root = StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[seed_node(), trip(seed_node())],
    )

    assert copy_refusal(root) == (
        "c_signal appears twice in the tree. A subtree the tree already states is "
        'stated again as {"kind": "copy", "inputs": [<that subtree>]}, and the '
        "build gives the copy steps of its own."
    )


def test_a_copy_that_differs_from_the_subtree_it_restates_is_refused() -> None:
    unioned = seed_node().model_copy(update={"operator": CombineOp.UNION})
    root = StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[seed_node(), trip(copy_of(unioned))],
    )

    assert copy_refusal(root) == (
        "A copy restates a subtree the tree states outside a copy, node for node: "
        "the same kinds, criteria and operators. Copy that subtree as it stands."
    )


def test_a_copy_with_no_input_is_refused() -> None:
    root = StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[seed_node(), trip(StructureNode(kind="copy"))],
    )

    assert copy_refusal(root) == (
        "A copy takes one input, the subtree it restates; "
        '{"kind": "copy", "inputs": [<the source subtree>]}.'
    )


def _carried(organism: str) -> StrategyStepNode:
    seed = StrategyStepNode(
        search_name="GenesWithSignalPeptide",
        parameters={"organism": MultiPickValue(values=[SOURCE])},
    )
    return StrategyStepNode(
        search_name=ORTHOLOGS,
        parameters={
            "organism": MultiPickValue(values=[organism]),
            "isSyntenic": SinglePickValue(value="no"),
        },
        primary_input=seed,
    )


def test_a_carry_changes_the_organism_of_the_records() -> None:
    assert organism_change(_carried(TARGET)) == OrganismChange(
        seed=[SOURCE], records=[TARGET]
    )


def test_a_round_trip_and_a_search_change_no_organism() -> None:
    built = build_step_tree(restate_copies(round_trip_spec())).root

    assert (
        organism_change(built),
        organism_change(_carried(SOURCE)),
        organism_change(StrategyStepNode(search_name="GenesByText")),
    ) == (None, None, None)


def test_the_change_reads_as_the_records_and_the_seed() -> None:
    change = OrganismChange(seed=[SOURCE], records=[TARGET])

    assert change.line() == f"{TARGET} (the seed searched {SOURCE})"


def test_a_criterion_the_copy_restates_keeps_its_values() -> None:
    restated = restate_copies(round_trip_spec())
    by_search: dict[str, list[Criterion]] = {}
    for criterion in restated.criteria:
        by_search.setdefault(criterion.search_name, []).append(criterion)

    first, second = by_search["GenesWithSignalPeptide"]
    assert first.resolved_params == second.resolved_params
    assert first.text == second.text
