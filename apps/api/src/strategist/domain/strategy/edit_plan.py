"""The plan an edit builds, and the tree it restates above the leaves.

The plan is the working graph the operations apply to as they are planned. A
structure that re-nests the steps that stay is restated as one tree instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StepKind,
    StrategyStepNode,
    generate_step_id,
    rebuild_tree,
)

from strategist.domain.strategy.combine_naming import (
    combine_display_name,
    combine_name,
)
from strategist.domain.strategy.combine_order import MIRRORED_OPERATORS, flat_join
from strategist.domain.strategy.operational_spec import (
    Criterion,
    StructureNode,
)
from strategist.domain.strategy.operations import GraphOperation, ReplaceSubtreeOp
from strategist.domain.strategy.operations.apply import apply_operation
from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.step_naming import criterion_title

__all__ = [
    "COPY_UNSTATED",
    "EditPlan",
    "LiveJoin",
    "UnsupportedEditError",
    "criterion_for",
    "live_join",
    "node_for",
    "restructure",
]


class UnsupportedEditError(Exception):
    """The edit does not map onto the steps the strategy already holds."""


COPY_UNSTATED = (
    "the edited structure holds a copy whose criteria are not all bound; a copy "
    "is stated as criteria of its own once every criterion it restates binds"
)


class LiveJoin(NamedTuple):
    step_id: str
    operator: CombineOp


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
        display_name=criterion_title(criterion).name,
    )


def criterion_for(plan: EditPlan, node: StructureNode) -> Criterion:
    criterion = plan.criteria.get(node.named_criterion)
    if criterion is None:
        msg = (
            f"structure names criterion {node.named_criterion!r}, which the spec lacks"
        )
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
    return _live_or_added_node(criterion, plan).model_copy(
        update={
            "primary_input": target(node.inputs[0], plan),
            "secondary_input": None,
        }
    )


def _target_combine(node: StructureNode, plan: EditPlan) -> StrategyStepNode:
    left = target(node.inputs[0], plan)
    for extra in node.inputs[1:]:
        left = _target_join(plan, left, target(extra, plan), node.combine_operator)
    return left


def _target_join(
    plan: EditPlan,
    left: StrategyStepNode,
    right: StrategyStepNode,
    operator: CombineOp,
) -> StrategyStepNode:
    """The combine over the two branches: the live one, or a new one."""
    existing = live_join(plan.graph, left.id, right.id, operator)
    if existing is None:
        join = flat_join(
            left,
            right,
            operator,
            left_nests=left.primary_input is not None,
            right_nests=right.primary_input is not None,
        )
        return StrategyStepNode(
            id=generate_step_id(),
            search_name=COMBINE_SEARCH_NAME,
            operator=join.operator,
            display_name=combine_display_name(join.operator),
            primary_input=join.primary,
            secondary_input=join.secondary,
        )
    live = plan.graph.steps[existing.step_id]
    primary, secondary = (
        (left, right) if live.primary_input_id == left.id else (right, left)
    )
    return rebuild_tree(live.id, plan.graph.steps).model_copy(
        update={
            "operator": existing.operator,
            "display_name": combine_name(
                live.display_name, live.search_name, existing.operator
            ),
            "colocation_params": (
                live.colocation_params if live.operator is existing.operator else None
            ),
            "primary_input": primary,
            "secondary_input": secondary,
        }
    )


def live_join(
    graph: StrategyGraph, left_id: str, right_id: str, operator: CombineOp
) -> LiveJoin | None:
    for step in graph.steps.values():
        if step.kind is not StepKind.COMBINE:
            continue
        held = (step.primary_input_id, step.secondary_input_id)
        if held == (left_id, right_id):
            return LiveJoin(step.id, operator)
        mirrored = MIRRORED_OPERATORS.get(operator)
        if held == (right_id, left_id) and mirrored is not None:
            return LiveJoin(step.id, mirrored)
    return None
