"""What every planned edit owes the strategy, over arbitrary trees.

One random edit is stated over a random strategy, planned and applied. The
steps the edit never named keep their ids, searches and values; the applied
graph has the shape the edited structure states; nothing is left unreachable;
and re-stating the same edit asks for no operation at all.
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from veupathdb.domain.parameters import NumberValue, ParamValue, to_wire
from veupathdb.domain.strategy import CombineOp, StepKind, StrategyStepNode

from pathfinder.domain.strategy.edit_plan import UnsupportedEditError
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_reconciliation import spec_without_steps
from pathfinder.tests.unit.domain.strategy._builders import (
    applied,
    combine,
    graph_of,
    leaf,
    plan,
    shape,
    spec_joined,
    spec_leaf,
    spec_of,
    strategy_trees,
    transform,
)

PROFILE = settings(max_examples=60, deadline=None)


def _nodes(node: StructureNode) -> list[StructureNode]:
    """Every node of a structure, the root first."""
    return [node, *(found for child in node.inputs for found in _nodes(child))]


def _replaced(
    node: StructureNode, target: StructureNode, replacement: StructureNode
) -> StructureNode:
    """The structure with one node swapped for another."""
    if node is target:
        return replacement
    return node.model_copy(
        update={"inputs": [_replaced(c, target, replacement) for c in node.inputs]}
    )


def _structure_shape(node: StructureNode) -> str:
    """The structure rendered the way ``shape`` renders a live graph."""
    if node.kind == "leaf":
        return node.criterion_id or "?"
    if node.kind == "transform":
        inner = _structure_shape(node.inputs[0])
        return f"{node.criterion_id}[{inner}]"
    rendered = _structure_shape(node.inputs[0])
    for extra in node.inputs[1:]:
        rendered = f"({rendered} {node.operator} {_structure_shape(extra)})"
    return rendered


def _reachable(graph: StrategyGraph) -> set[str]:
    root = graph.primary_root_id()
    assert root is not None
    seen: set[str] = set()
    stack = [root]
    while stack:
        step_id = stack.pop()
        if step_id in seen:
            continue
        seen.add(step_id)
        stack.extend(graph.steps[step_id].input_ids())
    return seen


def _searchable(spec: OperationalSpec, graph: StrategyGraph) -> list[str]:
    """The criteria that answer to a step running a search of its own."""
    return [
        c.id
        for c in spec.criteria
        if c.id in graph.steps and graph.steps[c.id].kind is not StepKind.COMBINE
    ]


def _values(graph: StrategyGraph, step_ids: set[str]) -> dict[str, dict[str, str]]:
    return {
        step_id: {
            name: to_wire(value)
            for name, value in graph.steps[step_id].parameters.items()
        }
        for step_id in step_ids
    }


def _searches(graph: StrategyGraph, step_ids: set[str]) -> dict[str, str | None]:
    return {step_id: graph.steps[step_id].search_name for step_id in step_ids}


def _fresh_id(graph: StrategyGraph) -> str:
    """An id the generator cannot mint: its ids are at most eight characters."""
    return f"added_leaf{len(graph.steps)}"


def _with_a_new_leaf(
    spec: OperationalSpec, graph: StrategyGraph, position: int
) -> tuple[OperationalSpec, str]:
    """The spec joining one new criterion beside a node the position names."""
    assert spec.structure is not None
    new_id = _fresh_id(graph)
    nodes = _nodes(spec.structure.root)
    target = nodes[position % len(nodes)]
    after = spec.model_copy(deep=True)
    assert after.structure is not None
    same = _nodes(after.structure.root)[nodes.index(target)]
    after.criteria.append(
        Criterion(id=new_id, text="a new filter", search_name="GenesByPfam")
    )
    after.structure = SpecStructure(
        root=_replaced(
            after.structure.root,
            same,
            spec_joined(CombineOp.INTERSECT, same, spec_leaf(new_id)),
        )
    )
    return after, new_id


def _with_one_value_moved(
    spec: OperationalSpec, target: str
) -> tuple[OperationalSpec, ParamValue]:
    after = spec.model_copy(deep=True)
    moved = NumberValue(value=7)
    for criterion in after.criteria:
        if criterion.id == target:
            criterion.resolved_params = {
                **criterion.resolved_params,
                "moved_value": moved,
            }
    return after, moved


def _joined_to_one_leaf(root: StrategyStepNode) -> StrategyStepNode:
    """The tree under a combine, so every example holds one and can lose one.

    The two ids are nine characters, which the generator's eight-character
    alphabet cannot produce, so the wrap never collides.
    """
    return combine("wrap_root", root, leaf("wrap_leaf"))


def _droppable(graph: StrategyGraph) -> list[str]:
    """The steps a drop removes on their own: a search under a combine."""
    return [
        step_id
        for step_id, step in graph.steps.items()
        if step.kind is not StepKind.COMBINE
        and (parent := graph.parent_of(step_id)) is not None
        and parent[0].kind is StepKind.COMBINE
    ]


def _with_one_operator_flipped(spec: OperationalSpec, position: int) -> OperationalSpec:
    after = spec.model_copy(deep=True)
    assert after.structure is not None
    combines = [n for n in _nodes(after.structure.root) if n.kind == "combine"]
    chosen = combines[position % len(combines)]
    chosen.operator = (
        CombineOp.UNION
        if chosen.operator is CombineOp.INTERSECT
        else CombineOp.INTERSECT
    )
    return after


def _planned(
    before: OperationalSpec, after: OperationalSpec, root: StrategyStepNode
) -> tuple[StrategyGraph, list[object]] | None:
    """The graph the plan leaves, or nothing when the planner refuses the edit.

    ``run_edit`` answers both of these with the same refusal, so a property
    about what an accepted plan guarantees passes over both.
    """
    try:
        ops = plan(before, after, graph_of(root))
    except UnsupportedEditError, ApplyError:
        return None
    return applied(root, ops), list(ops)


def test_dropping_a_root_transform_keeps_the_step_it_consumed() -> None:
    """The transform goes and the branch it read becomes the strategy's root."""
    root = transform("t0", combine("c0", leaf("a"), leaf("b")))
    before = spec_of(root)
    after = spec_without_steps(before, {"t0"})
    ops = plan(before, after, graph_of(root))

    after_graph = applied(root, ops)

    assert sorted(after_graph.steps) == ["a", "b", "c0"]
    assert after_graph.primary_root_id() == "c0"


def _kept_everything(
    root: StrategyStepNode, after_graph: StrategyGraph, named: set[str]
) -> None:
    """Every step the edit did not name kept its id, its search and its values."""
    before_graph = graph_of(root)
    untouched = set(before_graph.steps) & set(after_graph.steps) - named
    assert _searches(before_graph, untouched) == _searches(after_graph, untouched)
    assert _values(before_graph, untouched) == _values(after_graph, untouched)


def _holds_the_shape(after: OperationalSpec, after_graph: StrategyGraph) -> None:
    assert after.structure is not None
    assert shape(after_graph) == _structure_shape(after.structure.root)
    assert _reachable(after_graph) == set(after_graph.steps)


def _is_idempotent(after: OperationalSpec, after_graph: StrategyGraph) -> None:
    assert plan(after, after, after_graph) == []


@PROFILE
@given(root=strategy_trees(), position=st.integers(min_value=0, max_value=20))
def test_a_new_leaf_leaves_every_other_step_exactly_as_it_was(
    root: StrategyStepNode, position: int
) -> None:
    before = spec_of(root)
    graph = graph_of(root)
    after, new_id = _with_a_new_leaf(before, graph, position)
    result = _planned(before, after, root)
    assume(result is not None)
    assert result is not None
    after_graph, ops = result

    _kept_everything(root, after_graph, {new_id})
    _holds_the_shape(after, after_graph)
    _is_idempotent(after, after_graph)
    assert new_id in after_graph.steps
    assert len(ops) >= 1


@PROFILE
@given(root=strategy_trees(), position=st.integers(min_value=0, max_value=20))
def test_one_value_moved_reaches_its_step_and_no_other(
    root: StrategyStepNode, position: int
) -> None:
    before = spec_of(root)
    graph = graph_of(root)
    targets = _searchable(before, graph)
    assume(targets)
    target = targets[position % len(targets)]
    after, moved = _with_one_value_moved(before, target)
    result = _planned(before, after, root)
    assume(result is not None)
    assert result is not None
    after_graph, ops = result

    _kept_everything(root, after_graph, {target})
    _holds_the_shape(after, after_graph)
    _is_idempotent(after, after_graph)
    assert after_graph.steps[target].parameters["moved_value"] == moved
    assert [getattr(op, "kind", "") for op in ops] == ["updateStepParams"]


@PROFILE
@given(root=strategy_trees(), position=st.integers(min_value=0, max_value=20))
def test_one_dropped_leaf_takes_only_its_own_subtree(
    root: StrategyStepNode, position: int
) -> None:
    root = _joined_to_one_leaf(root)
    before = spec_of(root)
    graph = graph_of(root)
    targets = _droppable(graph)
    target = targets[position % len(targets)]
    after = spec_without_steps(before, {target})
    assert after.structure is not None
    assert len(after.criteria) == len(before.criteria) - 1
    result = _planned(before, after, root)
    assume(result is not None)
    assert result is not None
    after_graph, _ops = result

    _kept_everything(root, after_graph, {target})
    _holds_the_shape(after, after_graph)
    _is_idempotent(after, after_graph)
    assert set(after_graph.steps) == set(graph.steps) & set(after_graph.steps)
    assert target not in after_graph.steps


@PROFILE
@given(root=strategy_trees(), position=st.integers(min_value=0, max_value=20))
def test_one_flipped_operator_moves_that_combine_and_nothing_else(
    root: StrategyStepNode, position: int
) -> None:
    root = _joined_to_one_leaf(root)
    before = spec_of(root)
    after = _with_one_operator_flipped(before, position)
    result = _planned(before, after, root)
    assume(result is not None)
    assert result is not None
    after_graph, _ops = result

    _kept_everything(root, after_graph, set())
    _holds_the_shape(after, after_graph)
    _is_idempotent(after, after_graph)
    assert set(after_graph.steps) == set(graph_of(root).steps)
