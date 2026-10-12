"""Exports that land in any order end on the result the structure plans."""

from __future__ import annotations

import random

from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.ai.tools.standalone._eda_step_write import StepJoin, join_write
from pathfinder.domain.strategy.join_point import branch_step, join_point
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations import AddLeafOp, AttachNewRoot
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_reconciliation import spec_without_steps
from pathfinder.tests.unit.domain.strategy._builders import (
    combine,
    graph_with,
    leaf,
    shape,
    spec_joined,
    spec_leaf,
)

_OPERATORS = (
    CombineOp.INTERSECT,
    CombineOp.UNION,
    CombineOp.UNION,
    CombineOp.INTERSECT,
    CombineOp.MINUS,
)
_PLANS = 300
_MOST_INPUTS = 4
_MOST_MINUS_INPUTS = 3
_MOST_CRITERIA = 7


def _random_plan(rnd: random.Random, ids: list[str]) -> StructureNode:
    if len(ids) == 1:
        return spec_leaf(ids[0])
    operator = rnd.choice(_OPERATORS)
    most = _MOST_MINUS_INPUTS if operator is CombineOp.MINUS else _MOST_INPUTS
    cuts = sorted(
        rnd.sample(range(1, len(ids)), rnd.randint(2, min(most, len(ids))) - 1)
    )
    parts = [ids[a:b] for a, b in zip([0, *cuts], [*cuts, len(ids)], strict=True)]
    return spec_joined(operator, *(_random_plan(rnd, part) for part in parts))


def _spec_of(plan: StructureNode, ids: list[str]) -> OperationalSpec:
    return OperationalSpec(
        goal="g",
        criteria=[Criterion(id=c, text=c, search_name="GenesByTaxon") for c in ids],
        structure=SpecStructure(root=plan),
    )


def _folded(node: StructureNode, counter: list[int]) -> StrategyStepNode:
    if node.kind == "leaf":
        return leaf(node.named_criterion)
    step = _folded(node.inputs[0], counter)
    for extra in node.inputs[1:]:
        counter[0] += 1
        step = combine(
            f"step_j{counter[0]}",
            step,
            _folded(extra, counter),
            node.combine_operator,
        )
    return step


def _genes_of_the_plan(
    node: StructureNode, genes: dict[str, frozenset[int]]
) -> frozenset[int]:
    if node.kind == "leaf":
        return genes[node.named_criterion]
    found = _genes_of_the_plan(node.inputs[0], genes)
    for extra in node.inputs[1:]:
        found = _combined(
            node.combine_operator, found, _genes_of_the_plan(extra, genes)
        )
    return found


def _genes_of_the_strategy(
    graph: StrategyGraph, step_id: str, genes: dict[str, frozenset[int]]
) -> frozenset[int]:
    step = graph.steps[step_id]
    if step.operator is None:
        return genes[step_id]
    left, right = step.input_ids()
    return _combined(
        step.operator,
        _genes_of_the_strategy(graph, left, genes),
        _genes_of_the_strategy(graph, right, genes),
    )


def _combined(
    operator: CombineOp, left: frozenset[int], right: frozenset[int]
) -> frozenset[int]:
    if operator is CombineOp.INTERSECT:
        return left & right
    if operator is CombineOp.UNION:
        return left | right
    return left - right


def _export(graph: StrategyGraph, plan: SpecStructure, criterion_id: str) -> None:
    node = leaf(criterion_id)
    if not graph.steps:
        apply_operation(graph, AddLeafOp(step=node, attach=AttachNewRoot()))
        return
    point = join_point(plan, graph.steps, criterion_id)
    assert point is not None
    anchor = branch_step(graph, plan, point.anchor)
    assert anchor is not None
    join = StepJoin(anchor, point.operator, export_first=point.comes_first)
    for op in join_write(graph, node, join).ops:
        apply_operation(graph, op)


def test_exports_in_any_order_end_on_the_planned_result() -> None:
    rnd = random.Random(11)
    exports = 0
    for _ in range(_PLANS):
        ids = [f"step_{n}" for n in range(rnd.randint(2, _MOST_CRITERIA))]
        spec = _spec_of(_random_plan(rnd, ids), ids)
        plan = spec.structure
        assert plan is not None
        waiting = rnd.sample(ids, rnd.randint(1, len(ids)))
        built = spec_without_steps(spec, waiting).structure
        graph = graph_with([] if built is None else [_folded(built.root, [0])])
        genes = {
            c: frozenset(rnd.randrange(40) for _ in range(rnd.randint(5, 25)))
            for c in ids
        }
        for done, criterion_id in enumerate(waiting, start=1):
            _export(graph, plan, criterion_id)
            exports += 1
            held = spec_without_steps(spec, waiting[done:]).structure
            assert held is not None
            assert len(graph.roots) == 1, (plan, waiting[:done])
            root_id = graph.primary_root_id() or ""
            assert _genes_of_the_strategy(graph, root_id, genes) == _genes_of_the_plan(
                held.root, genes
            ), (plan, waiting[:done], shape(graph))
        assert set(ids) <= set(graph.steps)
    assert exports > _PLANS
