"""Turn a spec diff into operations over the strategy that already exists.

A step the edit does not name is not rewritten, so its WDK id and any value the
researcher set by hand survive the turn. An edit the operation algebra cannot
express is refused rather than approximated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from veupathdb.domain.strategy.ast import (
    COMBINE_SEARCH_NAME,
    StrategyStepNode,
    generate_step_id,
)
from veupathdb.domain.strategy.graph_model import StepKind, rebuild_tree
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.tree import subtree_ids

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    StructureNode,
    structure_criteria,
)
from pathfinder.domain.strategy.operations import (
    AddCombineOp,
    AddLeafOp,
    AddTransformOp,
    AttachNewRoot,
    DeleteStepOp,
    GraphOperation,
    ReplaceSubtreeOp,
    UpdateCombineOperatorOp,
    UpdateStepParamsOp,
    WireInputOp,
)
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.operations.resolutions import compute_delete_choices
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_diff import SpecDiff
from pathfinder.domain.strategy.stated_shape import (
    criteria_with_steps,
    stated_shape,
    working_copy,
)

__all__ = ["UnsupportedEditError", "operations_for"]

_MIN_COMBINE_INPUTS = 2


class UnsupportedEditError(Exception):
    """The edit does not map onto the steps the strategy already holds."""


@dataclass
class _Plan:
    """The operations so far, and the graph they have already been applied to."""

    graph: StrategyGraph
    ops: list[GraphOperation] = field(default_factory=list)
    added: frozenset[str] = frozenset()
    criteria: dict[str, Criterion] = field(default_factory=dict)
    stated: frozenset[str] = frozenset()
    """The criteria that answer to a step, which is what the shape measures."""
    rewires: bool = False
    """The structure states a wiring the live graph does not hold."""

    def emit(self, op: GraphOperation) -> None:
        self.ops.append(op)
        apply_operation(self.graph, op)


def operations_for(
    diff: SpecDiff,
    *,
    before: OperationalSpec,
    after: OperationalSpec,
    graph: StrategyGraph,
) -> list[GraphOperation]:
    """The smallest batch of graph operations that turns ``before`` into ``after``."""
    if after.structure is None:
        msg = "the edited spec states no structure"
        raise UnsupportedEditError(msg)
    entry_root = graph.primary_root_id()
    if entry_root is None:
        msg = "the strategy has no root step to edit"
        raise UnsupportedEditError(msg)
    outside = set(graph.steps) - set(subtree_ids(entry_root, graph.steps))
    plan = _plan_the_named_changes(diff, before=before, after=after, graph=graph)
    root_id = _resolve(after.structure.root, plan)
    if plan.rewires or root_id != plan.graph.primary_root_id():
        # The structure re-nests steps that stay, which no sequence of wiring
        # operations expresses: the combines above the leaves are restated.
        plan = _plan_the_named_changes(diff, before=before, after=after, graph=graph)
        root_id = _restructure(after.structure.root, plan)
    _refuse_a_shape_the_edit_did_not_state(plan, root_id, outside)
    return plan.ops


def _plan_the_named_changes(
    diff: SpecDiff,
    *,
    before: OperationalSpec,
    after: OperationalSpec,
    graph: StrategyGraph,
) -> _Plan:
    """A fresh plan holding the drops and the changes the diff names."""
    plan = _Plan(
        graph=working_copy(graph),
        added=frozenset(
            c.criterion_id for c in diff.changes if c.disposition == "added"
        ),
        criteria={c.id: c for c in after.criteria},
        stated=criteria_with_steps(
            [c.id for c in after.criteria],
            graph.steps,
            minted=structure_criteria(after.structure),
        ),
    )
    before_by_id = {c.id: c for c in before.criteria}
    # A criterion the structure leaves out binds an option on another
    # criterion's search, so the strategy holds no step of its own to change or
    # to delete.
    for change in diff.changes:
        if change.disposition == "dropped" and change.criterion_id in plan.graph.steps:
            plan.emit(_delete_op(plan.graph, change.criterion_id))
    for change in diff.changes:
        if change.disposition == "changed" and change.criterion_id in plan.graph.steps:
            plan.emit(
                _change_op(
                    plan.graph,
                    before_by_id[change.criterion_id],
                    plan.criteria[change.criterion_id],
                )
            )
    return plan


def _refuse_a_shape_the_edit_did_not_state(
    plan: _Plan, root_id: str, outside: set[str]
) -> None:
    """The planned graph holds exactly the criteria the edited spec names.

    ``outside`` are the steps the edited strategy did not reach when the turn
    began. They stay where they are: the edit neither adopts nor strands them.
    """
    shape = stated_shape(
        graph=plan.graph,
        root_id=root_id,
        criteria=plan.stated,
        outside=outside,
    )
    if shape.roots_elsewhere:
        msg = (
            f"the planned strategy roots at "
            f"{shape.live_root_id!r} where the edited structure "
            f"states {root_id!r}"
        )
        raise UnsupportedEditError(msg)
    if shape.adopted:
        msg = (
            f"the edit would adopt {list(shape.adopted)} from outside "
            f"the strategy it edits"
        )
        raise UnsupportedEditError(msg)
    if shape.lost or shape.unstated:
        msg = (
            f"the planned strategy holds {list(shape.searches)} where the "
            f"edited spec states {sorted(plan.stated)}"
        )
        raise UnsupportedEditError(msg)
    if shape.stranded:
        msg = f"the edit would strand {list(shape.stranded)} outside the strategy"
        raise UnsupportedEditError(msg)


def _delete_op(graph: StrategyGraph, step_id: str) -> DeleteStepOp:
    """The delete the structure implies, from the algebra that computes them."""
    choices = compute_delete_choices(graph, step_id)
    if not choices:
        msg = f"criterion {step_id!r} names no step to delete"
        raise UnsupportedEditError(msg)
    chosen = next((c for c in choices if c.is_default), choices[0])
    return DeleteStepOp(step_id=step_id, resolution=chosen.resolution)


def _change_op(
    graph: StrategyGraph, before: Criterion, after: Criterion
) -> GraphOperation:
    removed = set(before.resolved_params) - set(after.resolved_params)
    if before.search_name == after.search_name and not removed:
        return UpdateStepParamsOp(
            step_id=after.id, parameters=dict(after.resolved_params)
        )
    # An update merges, so a search change and a removed value both need the
    # node restated. The inputs come from the live subtree and stay attached.
    subtree = rebuild_tree(after.id, graph.steps).model_copy(
        update={
            "search_name": after.search_name,
            "parameters": dict(after.resolved_params),
            "display_name": after.text[:60],
        }
    )
    return ReplaceSubtreeOp(step_id=after.id, subtree=subtree)


def _node_for(criterion: Criterion) -> StrategyStepNode:
    return StrategyStepNode(
        id=criterion.id,
        search_name=criterion.search_name,
        parameters=dict(criterion.resolved_params),
        display_name=criterion.text[:60],
    )


def _criterion(plan: _Plan, node: StructureNode) -> Criterion:
    criterion = plan.criteria.get(node.criterion_id or "")
    if criterion is None:
        msg = f"structure names criterion {node.criterion_id!r}, which the spec lacks"
        raise UnsupportedEditError(msg)
    return criterion


def _resolve(node: StructureNode, plan: _Plan) -> str:
    """The step the node describes, adding it when the edit introduces it."""
    if node.kind == "leaf":
        return _resolve_leaf(node, plan)
    if node.kind == "transform":
        return _resolve_transform(node, plan)
    return _resolve_combine(node, plan)


def _resolve_leaf(node: StructureNode, plan: _Plan) -> str:
    criterion = _criterion(plan, node)
    if criterion.id in plan.graph.steps:
        return criterion.id
    if criterion.id not in plan.added:
        msg = f"criterion {criterion.id!r} names no step in the strategy"
        raise UnsupportedEditError(msg)
    plan.emit(AddLeafOp(step=_node_for(criterion), attach=AttachNewRoot()))
    return criterion.id


def _resolve_transform(node: StructureNode, plan: _Plan) -> str:
    criterion = _criterion(plan, node)
    if not node.inputs:
        msg = f"transform {criterion.id!r} states no input step"
        raise UnsupportedEditError(msg)
    input_id = _resolve(node.inputs[0], plan)
    existing = plan.graph.steps.get(criterion.id)
    if existing is not None:
        if existing.primary_input_id != input_id:
            plan.rewires = True
        return criterion.id
    if criterion.id not in plan.added:
        msg = f"criterion {criterion.id!r} names no step in the strategy"
        raise UnsupportedEditError(msg)
    consumer = plan.graph.parent_of(input_id)
    plan.emit(
        AddTransformOp(
            step=_node_for(criterion),
            input_id=input_id,
            mode="before-consumer" if consumer is not None else "new-root",
        )
    )
    return criterion.id


def _resolve_combine(node: StructureNode, plan: _Plan) -> str:
    if len(node.inputs) == 1:
        return _resolve(node.inputs[0], plan)
    if node.operator is None or len(node.inputs) < _MIN_COMBINE_INPUTS:
        msg = "a combine states an operator and at least two inputs"
        raise UnsupportedEditError(msg)
    left = _resolve(node.inputs[0], plan)
    for extra in node.inputs[1:]:
        right = _resolve(extra, plan)
        left = _join(plan, left, right, node.operator)
    return left


def _join(plan: _Plan, left_id: str, right_id: str, operator: CombineOp) -> str:
    """The combine over the two branches: the live one, or a new one."""
    existing = _combine_step_id(plan.graph, left_id, right_id)
    if existing is not None:
        if plan.graph.steps[existing].operator is not operator:
            plan.emit(UpdateCombineOperatorOp(step_id=existing, operator=operator))
        return existing
    consumer = plan.graph.parent_of(left_id)
    new_id = generate_step_id()
    plan.emit(
        AddCombineOp(
            step=StrategyStepNode(
                id=new_id,
                search_name=COMBINE_SEARCH_NAME,
                operator=operator,
            ),
            left_id=left_id,
            right_id=right_id,
        )
    )
    if consumer is not None:
        parent, _ = consumer
        plan.emit(
            WireInputOp(
                target_step_id=parent.id,
                slot="primary" if parent.primary_input_id == left_id else "secondary",
                source_step_id=new_id,
            )
        )
    return new_id


def _restructure(node: StructureNode, plan: _Plan) -> str:
    """Restate the combines above the leaves as one replacement at the root.

    Every leaf the structure names keeps the step id it already has, and a
    combine over an ordered pair the structure leaves alone keeps its own.
    """
    root_id = plan.graph.primary_root_id()
    if root_id is None:
        msg = "the strategy has no root step to edit"
        raise UnsupportedEditError(msg)
    target = _target(node, plan)
    plan.emit(ReplaceSubtreeOp(step_id=root_id, subtree=target))
    return target.id


def _target(node: StructureNode, plan: _Plan) -> StrategyStepNode:
    """The node the restated tree holds for this structure node."""
    if node.kind == "leaf":
        return _live_or_added_node(_criterion(plan, node), plan)
    if node.kind == "transform":
        return _target_transform(node, plan)
    return _target_combine(node, plan)


def _live_or_added_node(criterion: Criterion, plan: _Plan) -> StrategyStepNode:
    """The step the strategy already holds, or the one the edit introduces."""
    if criterion.id in plan.graph.steps:
        return rebuild_tree(criterion.id, plan.graph.steps)
    if criterion.id not in plan.added:
        msg = f"criterion {criterion.id!r} names no step in the strategy"
        raise UnsupportedEditError(msg)
    return _node_for(criterion)


def _target_transform(node: StructureNode, plan: _Plan) -> StrategyStepNode:
    criterion = _criterion(plan, node)
    if not node.inputs:
        msg = f"transform {criterion.id!r} states no input step"
        raise UnsupportedEditError(msg)
    return _live_or_added_node(criterion, plan).model_copy(
        update={
            "primary_input": _target(node.inputs[0], plan),
            "secondary_input": None,
        }
    )


def _target_combine(node: StructureNode, plan: _Plan) -> StrategyStepNode:
    if len(node.inputs) == 1:
        return _target(node.inputs[0], plan)
    if node.operator is None or len(node.inputs) < _MIN_COMBINE_INPUTS:
        msg = "a combine states an operator and at least two inputs"
        raise UnsupportedEditError(msg)
    left = _target(node.inputs[0], plan)
    for extra in node.inputs[1:]:
        left = _target_join(plan, left, _target(extra, plan), node.operator)
    return left


def _target_join(
    plan: _Plan,
    left: StrategyStepNode,
    right: StrategyStepNode,
    operator: CombineOp,
) -> StrategyStepNode:
    """The combine over the two branches: the live one, or a new one."""
    existing = _combine_step_id(plan.graph, left.id, right.id)
    if existing is None:
        return StrategyStepNode(
            id=generate_step_id(),
            search_name=COMBINE_SEARCH_NAME,
            operator=operator,
            primary_input=left,
            secondary_input=right,
        )
    live = plan.graph.steps[existing]
    return rebuild_tree(existing, plan.graph.steps).model_copy(
        update={
            "operator": operator,
            "colocation_params": (
                live.colocation_params if live.operator is operator else None
            ),
            "primary_input": left,
            "secondary_input": right,
        }
    )


def _combine_step_id(graph: StrategyGraph, left_id: str, right_id: str) -> str | None:
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
