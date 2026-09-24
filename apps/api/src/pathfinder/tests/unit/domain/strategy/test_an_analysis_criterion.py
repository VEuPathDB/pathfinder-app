"""A criterion an exported analysis realizes: its meaning in the spec, its
document on the step."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp, flatten_tree

from pathfinder.domain.strategy.edit_plan import node_for
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    build_step_tree,
    fold_option_criteria,
    pending_analyses,
)
from pathfinder.domain.strategy.operations import ReplaceSubtreeOp
from pathfinder.domain.strategy.spec_diff import diff_specs
from pathfinder.domain.strategy.spec_hydration import root_join_operator
from pathfinder.domain.strategy.spec_reconciliation import (
    spec_without_pending_analyses,
)
from pathfinder.domain.strategy.spec_to_operations import operations_for

from ._analysis import EXPORTED, analysed, binding, exported_step, pending
from ._builders import graph_with

_KINASES = Criterion(id="step_k1", text="kinases", search_name="GenesByText")


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _joined(operator: CombineOp, *inputs: StructureNode) -> SpecStructure:
    return SpecStructure(
        root=StructureNode(kind="combine", operator=operator, inputs=list(inputs))
    )


def _spec(*criteria: Criterion, structure: SpecStructure) -> OperationalSpec:
    return OperationalSpec(goal="g", criteria=list(criteria), structure=structure)


def test_the_step_carries_the_document_the_criterion_does_not_state() -> None:
    spec = _spec(analysed(), structure=SpecStructure(root=_leaf(EXPORTED)))

    root = build_step_tree(spec).root

    assert spec.criteria[0].resolved_params == {}
    assert root.search_name == "GenesByEdaVizWithCompute"
    assert root.parameters == binding().step_parameters


def test_an_edit_adds_the_step_with_its_document() -> None:
    assert node_for(analysed()).parameters == binding().step_parameters


def test_a_diff_reads_another_document_of_the_same_meaning_as_kept() -> None:
    """The document states no more than the binding's meaning does."""
    before = _spec(analysed(), structure=SpecStructure(root=_leaf(EXPORTED)))
    after = _spec(
        analysed(bound=binding().model_copy(update={"step_parameters": {}})),
        structure=SpecStructure(root=_leaf(EXPORTED)),
    )

    assert [c.disposition for c in diff_specs(before, after).changes] == ["kept"]


def test_a_diff_reads_a_new_cut_as_a_restated_binding() -> None:
    before = _spec(analysed(), structure=SpecStructure(root=_leaf(EXPORTED)))
    after = _spec(
        analysed(bound=binding(significance=0.01)),
        structure=SpecStructure(root=_leaf(EXPORTED)),
    )

    change = diff_specs(before, after).changes[0]

    assert (change.disposition, change.rebound_search, change.changed_params) == (
        "changed",
        True,
        {},
    )


def test_a_restated_binding_writes_the_new_document_on_its_step() -> None:
    before = _spec(analysed(), structure=SpecStructure(root=_leaf(EXPORTED)))
    after = _spec(
        analysed(bound=binding(significance=0.01)),
        structure=SpecStructure(root=_leaf(EXPORTED)),
    )
    graph = graph_with([exported_step()])

    ops = operations_for(diff_specs(before, after), after=after, graph=graph)

    assert len(ops) == 1
    assert isinstance(ops[0], ReplaceSubtreeOp)
    assert ops[0].subtree.parameters == binding(significance=0.01).step_parameters


def test_a_criterion_waiting_for_its_analysis_leaves_the_rest_ready() -> None:
    spec = _spec(
        _KINASES,
        pending(),
        structure=_joined(CombineOp.INTERSECT, _leaf("step_k1"), _leaf(pending().id)),
    )

    assert spec.ready_to_build is True
    assert [c.id for c in pending_analyses(spec)] == ["c_24h_vs_36_up"]


def test_a_spec_that_only_waits_for_analyses_has_nothing_to_build() -> None:
    spec = _spec(pending(), structure=SpecStructure(root=_leaf(pending().id)))

    assert spec.ready_to_build is False


def test_the_fold_leaves_an_analysis_criterion_where_it_is() -> None:
    """Two exports share a search, and neither is an option of the other."""
    other = analysed("step_9e1f7a20", bound=binding(significance=0.01))
    spec = _spec(analysed(), other, structure=SpecStructure(root=_leaf(EXPORTED)))

    folded = fold_option_criteria(spec)

    assert folded.unplaced == ()
    assert [c.id for c in folded.spec.criteria] == [EXPORTED, "step_9e1f7a20"]


def test_the_spec_the_strategy_answers_to_waits_for_no_analysis() -> None:
    spec = _spec(
        analysed(),
        pending(),
        structure=_joined(CombineOp.INTERSECT, _leaf(EXPORTED), _leaf(pending().id)),
    )

    answered = spec_without_pending_analyses(spec)

    assert [c.id for c in answered.criteria] == [EXPORTED]
    assert answered.structure == SpecStructure(root=_leaf(EXPORTED))


class TestTheRootJoin:
    """Where an export takes a waiting criterion's place in the strategy."""

    def test_a_leaf_under_the_root_combine_joins_at_its_operator(self) -> None:
        structure = _joined(CombineOp.INTERSECT, _leaf(EXPORTED), _leaf("c_36"))

        assert root_join_operator(structure, "c_36") is CombineOp.INTERSECT

    def test_the_last_input_of_a_minus_joins_at_minus(self) -> None:
        structure = _joined(CombineOp.MINUS, _leaf(EXPORTED), _leaf("c_36"))

        assert root_join_operator(structure, "c_36") is CombineOp.MINUS

    def test_a_leaf_the_root_join_cannot_reach_has_no_join(self) -> None:
        """The first input of a MINUS, a leaf in a branch, and a lone leaf."""
        branch = StructureNode(
            kind="combine",
            operator=CombineOp.UNION,
            inputs=[_leaf(EXPORTED), _leaf("c_36")],
        )
        structures = [
            _joined(CombineOp.MINUS, _leaf("c_36"), _leaf(EXPORTED)),
            _joined(CombineOp.INTERSECT, branch, _leaf("step_k1")),
            SpecStructure(root=_leaf("c_36")),
        ]

        assert [root_join_operator(s, "c_36") for s in structures] == [
            None,
            None,
            None,
        ]


def test_the_steps_a_built_spec_mints_hold_every_analysis_document() -> None:
    spec = _spec(
        analysed(),
        analysed("step_9e1f7a20", bound=binding(significance=0.01)),
        structure=_joined(CombineOp.INTERSECT, _leaf(EXPORTED), _leaf("step_9e1f7a20")),
    )

    steps = flatten_tree(build_step_tree(spec).root)

    assert sorted(
        step.parameters["eda_analysis_spec"].model_dump_json()
        for step in steps.values()
        if step.search_name == "GenesByEdaVizWithCompute"
    ) == sorted(
        b.step_parameters["eda_analysis_spec"].model_dump_json()
        for b in (binding(), binding(significance=0.01))
    )
