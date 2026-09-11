"""A criterion the structure does not name binds an option, not a step.

The build mints a step for the criteria the structure names. A criterion that
names an option on another criterion's search answers to that criterion's step,
so no measurement and no refusal may ask it for a step of its own.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters.values import MultiPickValue, StringValue
from veupathdb.domain.strategy.graph_model import flatten_tree

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    build_step_tree,
    renumber_criteria,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_diff import diff_specs
from pathfinder.domain.strategy.spec_to_operations import (
    UnsupportedEditError,
    operations_for,
)
from pathfinder.domain.strategy.stated_shape import (
    criteria_with_steps,
    stated_shape,
    structure_criteria,
)

_EXPRESSION = "gametocyte_expression"
_OPTION = "gametocyte_timecourse_option"


def _framed() -> OperationalSpec:
    """Two criteria, one of which the structure does not name."""
    return OperationalSpec(
        goal="genes upregulated in gametocytes",
        record_type="transcript",
        criteria=[
            Criterion(
                id=_EXPRESSION,
                text="upregulated in gametocytes",
                search_name="GenesByRNASeqEvidence",
                resolved_params={"organism": MultiPickValue(values=["Pf3D7"])},
            ),
            Criterion(
                id=_OPTION,
                text="use the gametocyte timecourse dataset",
                search_name="GenesByRNASeqEvidence",
                resolved_params={"dataset": StringValue(value="timecourse")},
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id=_EXPRESSION)
        ),
    )


def _built() -> tuple[OperationalSpec, StrategyGraph]:
    spec = _framed()
    tree = build_step_tree(spec)
    graph = StrategyGraph(graph_id="g1", name="gametocytes", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(tree.root)
    graph.recompute_roots()
    graph.last_step_id = tree.root.id
    return renumber_criteria(spec, tree.step_id_by_criterion), graph


def _plan(
    before: OperationalSpec, after: OperationalSpec, graph: StrategyGraph
) -> list[str]:
    ops = operations_for(
        diff_specs(before, after), before=before, after=after, graph=graph
    )
    return [op.kind for op in ops]


def test_the_build_mints_no_step_for_a_criterion_the_structure_leaves_out() -> None:
    before, graph = _built()

    assert _OPTION not in graph.steps
    assert [c.id for c in before.criteria] == [graph.last_step_id, _OPTION]


def test_the_stated_criteria_are_the_ones_that_answer_to_a_step() -> None:
    before, graph = _built()

    stated = criteria_with_steps(
        [c.id for c in before.criteria],
        graph.steps,
        minted=structure_criteria(before.structure),
    )

    assert stated == frozenset({graph.last_step_id})


def test_an_added_criterion_answers_to_the_step_the_structure_states() -> None:
    """The edit mints its step, so the shape counts it before it exists."""
    before, graph = _built()

    stated = criteria_with_steps(
        [*(c.id for c in before.criteria), "new_leaf"],
        graph.steps,
        minted=structure_criteria(
            SpecStructure(
                root=StructureNode(
                    kind="combine",
                    operator=None,
                    inputs=[
                        StructureNode(kind="leaf", criterion_id=graph.last_step_id),
                        StructureNode(kind="leaf", criterion_id="new_leaf"),
                    ],
                )
            )
        ),
    )

    assert stated == frozenset({graph.last_step_id, "new_leaf"})


def test_an_option_criterion_is_never_reported_lost() -> None:
    before, graph = _built()

    shape = stated_shape(
        graph=graph,
        root_id=graph.primary_root_id() or "",
        criteria=criteria_with_steps(
            [c.id for c in before.criteria],
            graph.steps,
            minted=structure_criteria(before.structure),
        ),
        outside=set(),
    )

    assert shape.lost == ()
    assert shape.unstated == ()
    assert shape.holds is True


def test_an_edit_that_keeps_both_criteria_plans_nothing() -> None:
    before, graph = _built()

    assert _plan(before, before.model_copy(deep=True), graph) == []


def test_an_edit_that_restates_the_option_value_is_not_refused() -> None:
    """An option criterion owes no step, so restating its value is a valid edit."""
    before, graph = _built()
    after = before.model_copy(deep=True)
    for criterion in after.criteria:
        if criterion.id == _OPTION:
            criterion.resolved_params = {
                "dataset": StringValue(value="gametocyte_timecourse")
            }

    assert _plan(before, after, graph) == []


def test_an_edit_that_drops_the_option_criterion_plans_nothing() -> None:
    before, graph = _built()
    after = before.model_copy(deep=True)
    after.criteria = [c for c in after.criteria if c.id != _OPTION]

    assert _plan(before, after, graph) == []


def test_a_refusal_names_no_criterion_that_can_have_no_step() -> None:
    """A structure that states none of the live steps is still refused."""
    before, graph = _built()
    after = before.model_copy(deep=True)
    after.criteria = [
        *after.criteria,
        Criterion(id="added_leaf", text="a second search", search_name="GenesByTaxon"),
    ]
    after.structure = SpecStructure(
        root=StructureNode(kind="leaf", criterion_id="added_leaf")
    )

    with pytest.raises(UnsupportedEditError) as excinfo:
        _plan(before, after, graph)

    assert _OPTION not in str(excinfo.value)
