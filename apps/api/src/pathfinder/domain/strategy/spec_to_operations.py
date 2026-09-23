"""Turn a spec diff into operations over the strategy that already exists.

A step the edit does not name is not rewritten, so its WDK id and any value the
researcher set by hand survive the turn. An edit the operation algebra cannot
express is refused rather than approximated.
"""

from __future__ import annotations

from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StepKind,
    StrategyStepNode,
    generate_step_id,
    rebuild_tree,
    subtree_ids,
)

from pathfinder.domain.strategy.combine_naming import combine_display_name
from pathfinder.domain.strategy.edit_plan import (
    EditPlan,
    UnsupportedEditError,
    combine_step_id,
    criterion_for,
    node_for,
    restructure,
)
from pathfinder.domain.strategy.operational_spec import (
    MIN_COMBINE_INPUTS,
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
from pathfinder.domain.strategy.operations.resolutions import compute_delete_choices
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_diff import CriterionChange, SpecDiff
from pathfinder.domain.strategy.stated_shape import (
    StatedShape,
    criteria_with_steps,
    stated_shape,
    working_copy,
)

__all__ = ["criteria_the_edit_introduces", "operations_for"]


def operations_for(
    diff: SpecDiff,
    *,
    after: OperationalSpec,
    graph: StrategyGraph,
) -> list[GraphOperation]:
    """The smallest batch of graph operations the diff and ``after`` state.

    The diff is the whole account of what moved, so the spec the turn started
    from is not read again here.
    """
    if after.structure is None:
        msg = "the edited spec states no structure"
        raise UnsupportedEditError(msg)
    entry_root = graph.primary_root_id()
    if entry_root is None:
        msg = "the strategy has no root step to edit"
        raise UnsupportedEditError(msg)
    outside = set(graph.steps) - set(subtree_ids(entry_root, graph.steps))
    plan = _plan_the_named_changes(diff, after=after, graph=graph)
    root_id = _resolve(after.structure.root, plan)
    if plan.rewires or not _shape_of(plan, root_id, outside).holds:
        # The structure re-nests steps that stay, which no sequence of wiring
        # operations expresses: the combines above the leaves are restated.
        plan = _plan_the_named_changes(diff, after=after, graph=graph)
        root_id = restructure(after.structure.root, plan)
    _refuse_a_shape_the_edit_did_not_state(plan, root_id, outside)
    _refuse_a_removal_the_edit_did_not_state(plan, diff, graph, entry_root)
    return plan.ops


def criteria_the_edit_introduces(
    *, after: OperationalSpec, graph: StrategyGraph
) -> frozenset[str]:
    """The criteria this edit mints a step for.

    The strategy answers it: a criterion the edited structure states and the
    graph holds no step for is one the edit introduces, whatever the diff calls
    it. A criterion outside the structure binds an option and owns no step.
    """
    return frozenset(structure_criteria(after.structure) - set(graph.steps))


def _plan_the_named_changes(
    diff: SpecDiff,
    *,
    after: OperationalSpec,
    graph: StrategyGraph,
) -> EditPlan:
    """A fresh plan holding the drops and the changes the diff names."""
    added = criteria_the_edit_introduces(after=after, graph=graph)
    plan = EditPlan(
        graph=working_copy(graph),
        added=added,
        criteria={c.id: c for c in after.criteria},
        stated=criteria_with_steps(
            [c.id for c in after.criteria], graph.steps, minted=added
        ),
    )
    # A criterion the structure leaves out binds an option on another
    # criterion's search, so the strategy holds no step of its own to change or
    # to delete.
    for change in diff.changes:
        if change.disposition == "dropped" and change.criterion_id in plan.graph.steps:
            plan.emit(_delete_op(plan.graph, change.criterion_id))
    for change in diff.changes:
        if change.disposition == "changed" and change.criterion_id in plan.graph.steps:
            plan.emit(
                _change_op(plan.graph, change, plan.criteria[change.criterion_id])
            )
    return plan


def _shape_of(plan: EditPlan, root_id: str, outside: set[str]) -> StatedShape:
    """How the planned graph departs from the criteria the edited spec names.

    ``outside`` are the steps the edited strategy did not reach when the turn
    began. They stay where they are: the edit neither adopts nor strands them.
    """
    return stated_shape(
        graph=plan.graph,
        root_id=root_id,
        criteria=plan.stated,
        outside=outside,
    )


def _refuse_a_shape_the_edit_did_not_state(
    plan: EditPlan, root_id: str, outside: set[str]
) -> None:
    """The planned graph holds exactly the criteria the edited spec names."""
    shape = _shape_of(plan, root_id, outside)
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


def _the_drops_account_for(diff: SpecDiff, graph: StrategyGraph) -> set[str]:
    """The steps a dropped criterion takes with it.

    A criterion addresses the step it names and the subtree under it, which is
    how one criterion stands for a saved strategy the build expanded.
    """
    return {
        step_id
        for change in diff.changes
        if change.disposition == "dropped" and change.criterion_id in graph.steps
        for step_id in subtree_ids(change.criterion_id, graph.steps)
    }


def _refuse_a_removal_the_edit_did_not_state(
    plan: EditPlan, diff: SpecDiff, graph: StrategyGraph, entry_root: str
) -> None:
    """A step that runs a search leaves the strategy only when the edit drops it.

    A combine carries no criterion of its own, so the structure states where it
    goes and the plan restates it.
    """
    accounted = _the_drops_account_for(diff, graph)
    removed = sorted(
        step_id
        for step_id in subtree_ids(entry_root, graph.steps)
        if step_id not in plan.graph.steps
        and step_id not in accounted
        and graph.steps[step_id].kind is not StepKind.COMBINE
    )
    if removed:
        msg = (
            f"the edit would take {removed} off the strategy, and the edited "
            f"spec states no drop for them. State a criterion under each of "
            f"those step ids and name it in the structure to keep it, or drop "
            f"it with drop_criterion to remove it"
        )
        raise UnsupportedEditError(msg)


def _delete_op(graph: StrategyGraph, step_id: str) -> DeleteStepOp:
    """The delete the structure implies, from the algebra that computes them."""
    choices = compute_delete_choices(graph, step_id)
    if not choices:
        msg = f"criterion {step_id!r} names no step to delete"
        raise UnsupportedEditError(msg)
    chosen = next((c for c in choices if c.is_default), choices[0])
    return DeleteStepOp(step_id=step_id, resolution=chosen.resolution)


def _moved_values(change: CriterionChange, after: Criterion) -> dict[str, ParamValue]:
    """The values this change moved, as the edited spec states them."""
    return {
        name: value
        for name, value in after.resolved_params.items()
        if name in change.changed_params
    }


def _restated_params(
    graph: StrategyGraph, change: CriterionChange, after: Criterion
) -> dict[str, ParamValue]:
    """What the restated node carries when an update cannot express the change.

    A rebound search shares no values with the one it replaces, so the edited
    spec states the whole binding. A search that stays keeps the values its own
    step holds, less the ones the edit took away and plus the ones it moved.
    """
    if change.rebound_search:
        return dict(after.resolved_params)
    removed = set(change.removed_params)
    live = graph.steps[after.id].parameters
    return {
        **{name: value for name, value in live.items() if name not in removed},
        **_moved_values(change, after),
    }


def _change_op(
    graph: StrategyGraph, change: CriterionChange, after: Criterion
) -> GraphOperation:
    """The operation that moves what the diff says moved, and nothing else.

    A value the edit does not name stays as the step holds it, so a value the
    researcher set on the canvas survives an edit of another value.
    """
    if not change.rebound_search and not change.removed_params:
        return UpdateStepParamsOp(
            step_id=after.id, parameters=_moved_values(change, after)
        )
    # An update merges, so a search change and a removed value both need the
    # node restated. The inputs come from the live subtree and stay attached.
    live = rebuild_tree(after.id, graph.steps)
    subtree = live.model_copy(
        update={
            "search_name": after.search_name,
            "parameters": _restated_params(graph, change, after),
            # A step that keeps its search keeps its name; a new search is
            # titled by what now runs.
            "display_name": after.title if change.rebound_search else live.display_name,
        }
    )
    return ReplaceSubtreeOp(step_id=after.id, subtree=subtree)


def _resolve(node: StructureNode, plan: EditPlan) -> str:
    """The step the node describes, adding it when the edit introduces it."""
    if node.kind == "leaf":
        return _resolve_leaf(node, plan)
    if node.kind == "transform":
        return _resolve_transform(node, plan)
    return _resolve_combine(node, plan)


def _resolve_leaf(node: StructureNode, plan: EditPlan) -> str:
    criterion = criterion_for(plan, node)
    if criterion.id in plan.graph.steps:
        return criterion.id
    if criterion.id not in plan.added:
        msg = f"criterion {criterion.id!r} names no step in the strategy"
        raise UnsupportedEditError(msg)
    plan.emit(AddLeafOp(step=node_for(criterion), attach=AttachNewRoot()))
    return criterion.id


def _resolve_transform(node: StructureNode, plan: EditPlan) -> str:
    criterion = criterion_for(plan, node)
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
            step=node_for(criterion),
            input_id=input_id,
            mode="before-consumer" if consumer is not None else "new-root",
        )
    )
    return criterion.id


def _resolve_combine(node: StructureNode, plan: EditPlan) -> str:
    if len(node.inputs) == 1:
        return _resolve(node.inputs[0], plan)
    if node.operator is None or len(node.inputs) < MIN_COMBINE_INPUTS:
        msg = "a combine states an operator and at least two inputs"
        raise UnsupportedEditError(msg)
    left = _resolve(node.inputs[0], plan)
    for extra in node.inputs[1:]:
        right = _resolve(extra, plan)
        left = _join(plan, left, right, node.operator)
    return left


def _join(plan: EditPlan, left_id: str, right_id: str, operator: CombineOp) -> str:
    """The combine over the two branches: the live one, or a new one."""
    existing = combine_step_id(plan.graph, left_id, right_id)
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
                display_name=combine_display_name(operator),
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
