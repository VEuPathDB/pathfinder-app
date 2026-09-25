"""The plan an edit builds, and the tree it restates above the leaves.

The plan is the working graph the operations apply to as they are planned. A
structure that re-nests the steps that stay is restated as one tree instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StepKind,
    StrategyStepNode,
    generate_step_id,
    rebuild_tree,
)

from pathfinder.domain.strategy.combine_naming import (
    combine_display_name,
    combine_name,
)
from pathfinder.domain.strategy.operational_spec import (
    MIN_COMBINE_INPUTS,
    Criterion,
    StructureNode,
)
from pathfinder.domain.strategy.operations import GraphOperation, ReplaceSubtreeOp
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategyGraph

__all__ = [
    "COPY_UNSTATED",
    "EditPlan",
    "UnsupportedEditError",
    "combine_step_id",
    "criterion_for",
    "node_for",
    "restructure",
]


class UnsupportedEditError(Exception):
    """The edit does not map onto the steps the strategy already holds."""


COPY_UNSTATED = (
    "the edited structure holds a copy whose criteria are not all bound; a copy "
    "is stated as criteria of its own once every criterion it restates binds"
)


@dataclass
class EditPlan:
    """The operations so far, and the graph they have already been applied to."""

    graph: StrategyGraph
    ops: list[GraphOperation] = field(default_factory=list)
    added: frozenset[str] = frozenset()
    """The structure criteria the strategy holds no step for; the edit mints one."""
    criteria: dict[str, Criterion] = field(default_factory=dict)
    stated: frozenset[str] = frozenset()
    """The criteria that answer to a step, which is what the shape measures."""
    rewires: bool = False
    """The structure states a wiring the live graph does not hold."""

    def emit(self, op: GraphOperation) -> None:
        self.ops.append(op)
        apply_operation(self.graph, op)


def node_for(criterion: Criterion) -> StrategyStepNode:
    return StrategyStepNode(
        id=criterion.id,
        search_name=criterion.search_name,
        parameters=criterion.step_parameters,
        display_name=criterion.title,
    )


def criterion_for(plan: EditPlan, node: StructureNode) -> Criterion:
    criterion = plan.criteria.get(node.criterion_id or "")
    if criterion is None:
        msg = f"structure names criterion {node.criterion_id!r}, which the spec lacks"
        raise UnsupportedEditError(msg)
    return criterion


def restructure(node: StructureNode, plan: EditPlan) -> str:
    """Restate the combines above the leaves as one replacement at the root.

    Every leaf the structure names keeps the step id it already has, and a
    combine over an ordered pair the structure leaves alone keeps its own.
    """
    root_id = plan.graph.primary_root_id()
    if root_id is None:
        msg = "the strategy has no root step to edit"
        raise UnsupportedEditError(msg)
    restated = target(node, plan)
    plan.emit(ReplaceSubtreeOp(step_id=root_id, subtree=restated))
    return restated.id


def target(node: StructureNode, plan: EditPlan) -> StrategyStepNode:
    """The node the restated tree holds for this structure node."""
    if node.kind == "leaf":
        return _live_or_added_node(criterion_for(plan, node), plan)
    if node.kind == "transform":
        return _target_transform(node, plan)
    if node.kind == "copy":
        raise UnsupportedEditError(COPY_UNSTATED)
    return _target_combine(node, plan)


def _live_or_added_node(criterion: Criterion, plan: EditPlan) -> StrategyStepNode:
    """The step the strategy already holds, or the one the edit introduces."""
    if criterion.id in plan.graph.steps:
        return rebuild_tree(criterion.id, plan.graph.steps)
    if criterion.id not in plan.added:
        msg = f"criterion {criterion.id!r} names no step in the strategy"
        raise UnsupportedEditError(msg)
    return node_for(criterion)


def _target_transform(node: StructureNode, plan: EditPlan) -> StrategyStepNode:
    criterion = criterion_for(plan, node)
    if not node.inputs:
        msg = f"transform {criterion.id!r} states no input step"
        raise UnsupportedEditError(msg)
    return _live_or_added_node(criterion, plan).model_copy(
        update={
            "primary_input": target(node.inputs[0], plan),
            "secondary_input": None,
        }
    )


def _target_combine(node: StructureNode, plan: EditPlan) -> StrategyStepNode:
    if len(node.inputs) == 1:
        return target(node.inputs[0], plan)
    if node.operator is None or len(node.inputs) < MIN_COMBINE_INPUTS:
        msg = "a combine states an operator and at least two inputs"
        raise UnsupportedEditError(msg)
    left = target(node.inputs[0], plan)
    for extra in node.inputs[1:]:
        left = _target_join(plan, left, target(extra, plan), node.operator)
    return left


def _target_join(
    plan: EditPlan,
    left: StrategyStepNode,
    right: StrategyStepNode,
    operator: CombineOp,
) -> StrategyStepNode:
    """The combine over the two branches: the live one, or a new one."""
    existing = combine_step_id(plan.graph, left.id, right.id)
    if existing is None:
        return StrategyStepNode(
            id=generate_step_id(),
            search_name=COMBINE_SEARCH_NAME,
            operator=operator,
            display_name=combine_display_name(operator),
            primary_input=left,
            secondary_input=right,
        )
    live = plan.graph.steps[existing]
    return rebuild_tree(existing, plan.graph.steps).model_copy(
        update={
            "operator": operator,
            "display_name": combine_name(live.display_name, live.search_name, operator),
            "colocation_params": (
                live.colocation_params if live.operator is operator else None
            ),
            "primary_input": left,
            "secondary_input": right,
        }
    )


def combine_step_id(graph: StrategyGraph, left_id: str, right_id: str) -> str | None:
    return next(
        (
            step.id
            for step in graph.steps.values()
            if step.kind is StepKind.COMBINE
            and step.primary_input_id == left_id
            and step.secondary_input_id == right_id
        ),
        None,
    )
