"""A spec states the criteria the graph still holds a step for.

The graph editor and the assistant are two hands on one strategy. A step one
hand deletes must leave the spec the other hand starts its next turn from.
"""

from __future__ import annotations

from collections.abc import Collection

from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_reconciliation import spec_without_steps

_SIGNAL = "step_3fa0e628"
_TRANSMEMBRANE = "step_2ea81607"
_COMBINE = "step_3c07753b"


def _graph(root: StrategyStepNode | None) -> StrategyGraph:
    graph = StrategyGraph(graph_id="g1", name="signal peptide", site_id="plasmodb")
    graph.record_type = "transcript"
    if root is not None:
        graph.steps = flatten_tree(root)
    graph.recompute_roots()
    return graph


def _departed(spec: OperationalSpec, graph: StrategyGraph) -> Collection[str]:
    """The criteria of this spec the graph holds no step for."""
    return [c.id for c in spec.criteria if c.id not in graph.steps]


def _reconciled(spec: OperationalSpec, graph: StrategyGraph) -> OperationalSpec:
    """The spec without the criteria whose steps the graph lost."""
    return spec_without_steps(spec, _departed(spec, graph))


def _signal_step() -> StrategyStepNode:
    return StrategyStepNode(
        id=_SIGNAL,
        search_name="GenesBySignalPeptide",
        display_name="signal peptide",
    )


def _both_steps() -> StrategyStepNode:
    return StrategyStepNode(
        id=_COMBINE,
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=_signal_step(),
        secondary_input=StrategyStepNode(
            id=_TRANSMEMBRANE,
            search_name="GenesByTransmembraneDomains",
            display_name="at least one transmembrane domain",
        ),
    )


def _two_criteria() -> OperationalSpec:
    return OperationalSpec(
        goal="signal peptide and a transmembrane domain",
        criteria=[
            Criterion(
                id=_SIGNAL,
                text="signal peptide",
                search_name="GenesBySignalPeptide",
                role="seed",
            ),
            Criterion(
                id=_TRANSMEMBRANE,
                text="at least one transmembrane domain",
                search_name="GenesByTransmembraneDomains",
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id=_SIGNAL),
                    StructureNode(kind="leaf", criterion_id=_TRANSMEMBRANE),
                ],
            )
        ),
    )


def test_a_criterion_whose_step_the_graph_lost_leaves_the_spec() -> None:
    reconciled = _reconciled(_two_criteria(), _graph(_signal_step()))

    assert [c.id for c in reconciled.criteria] == [_SIGNAL]


def test_the_combine_left_with_one_input_collapses_to_that_input() -> None:
    reconciled = _reconciled(_two_criteria(), _graph(_signal_step()))

    assert reconciled.structure is not None
    assert reconciled.structure.root == StructureNode(kind="leaf", criterion_id=_SIGNAL)


def test_a_spec_every_step_of_which_the_graph_holds_is_unchanged() -> None:
    spec = _two_criteria()

    assert _reconciled(spec, _graph(_both_steps())) == spec


def test_an_emptied_strategy_leaves_no_criterion_and_no_structure() -> None:
    reconciled = _reconciled(_two_criteria(), _graph(None))

    assert reconciled.criteria == []
    assert reconciled.structure is None


def test_a_criterion_the_caller_does_not_name_stays() -> None:
    """An option criterion binds a value on another criterion's step."""
    spec = _two_criteria()
    spec.criteria.append(
        Criterion(
            id="sexual_stage_option",
            text="use the sexual stage dataset",
            search_name="GenesByRNASeqEvidence",
        )
    )

    reconciled = spec_without_steps(spec, {_TRANSMEMBRANE})

    assert [c.id for c in reconciled.criteria] == [_SIGNAL, "sexual_stage_option"]


def test_an_open_slot_of_a_departed_criterion_leaves_with_it() -> None:
    spec = _two_criteria()
    spec.open_slots = [OpenSlot(param_name="organism", criterion_id=_TRANSMEMBRANE)]

    reconciled = _reconciled(spec, _graph(_signal_step()))

    assert reconciled.open_slots == []


def test_a_transform_whose_step_left_collapses_to_its_input() -> None:
    spec = _two_criteria()
    spec.structure = SpecStructure(
        root=StructureNode(
            kind="transform",
            criterion_id=_TRANSMEMBRANE,
            inputs=[StructureNode(kind="leaf", criterion_id=_SIGNAL)],
        )
    )

    reconciled = _reconciled(spec, _graph(_signal_step()))

    assert reconciled.structure is not None
    assert reconciled.structure.root == StructureNode(kind="leaf", criterion_id=_SIGNAL)


def test_a_transform_left_with_no_input_leaves_with_its_criterion() -> None:
    """A transform states the step it consumes; with none it states nothing."""
    transform_id = "step_9ab41c7d"
    spec = OperationalSpec(
        goal="orthologs of the signal peptide genes",
        criteria=[
            Criterion(
                id=_SIGNAL,
                text="signal peptide",
                search_name="GenesBySignalPeptide",
                role="seed",
            ),
            Criterion(
                id=transform_id,
                text="orthologs in P. vivax",
                search_name="GenesByOrthologs",
                role="transform",
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="transform",
                criterion_id=transform_id,
                inputs=[StructureNode(kind="leaf", criterion_id=_SIGNAL)],
            )
        ),
    )
    graph = _graph(
        StrategyStepNode(
            id=transform_id,
            search_name="GenesByOrthologs",
            primary_input=StrategyStepNode(
                id="step_11111111", search_name="GenesByTaxon"
            ),
        )
    )

    reconciled = _reconciled(spec, graph)

    assert reconciled.criteria == []
    assert reconciled.structure is None
