"""Delete a step or an edge, and re-wire what the deletion leaves behind."""

from veupathdb.domain.strategy import StepKind, StrategyStep, subtree_ids

from pathfinder.domain.strategy.operations._graph_edit import (
    ApplyError,
    ApplyResult,
    _demote_to_single_input,
    _drop,
    _require,
    _set_input_slot,
    _settle,
)
from pathfinder.domain.strategy.operations.resolutions import (
    why_the_graph_refuses_the_delete,
)
from pathfinder.domain.strategy.operations.types import (
    DeleteEdgeOp,
    DeleteEdgeResolution,
    DeleteResolution,
    DeleteStepOp,
)
from pathfinder.domain.strategy.session import StrategyGraph


def _apply_delete_step(graph: StrategyGraph, op: DeleteStepOp) -> ApplyResult:
    refusal = why_the_graph_refuses_the_delete(graph, op)
    if refusal is not None:
        raise ApplyError(refusal)
    target = graph.steps[op.step_id]

    if op.resolution == DeleteResolution.DELETE_STRATEGY:
        dropped = sorted(graph.steps)
        graph.steps.clear()
        graph.roots.clear()
        graph.last_step_id = None
        return ApplyResult(description="Deleted strategy", dropped_step_ids=dropped)

    parent_info = graph.parent_of(op.step_id)

    if op.resolution == DeleteResolution.DELETE_SUBTREE:
        return _delete_subtree(graph, target, parent_info)
    if op.resolution == DeleteResolution.COLLAPSE_COMBINE:
        return _collapse_combine(graph, target, parent_info)
    if op.resolution == DeleteResolution.ORPHAN_SIBLING and parent_info is not None:
        return _orphan_sibling(graph, target, *parent_info)
    if op.resolution == DeleteResolution.PROMOTE_PRIMARY:
        return _promote_primary(graph, target, parent_info)

    msg = f"unhandled resolution {op.resolution!r}"
    raise ApplyError(msg)


def _delete_subtree(
    graph: StrategyGraph,
    target: StrategyStep,
    parent_info: tuple[StrategyStep, str] | None,
) -> ApplyResult:
    """Remove the branch, and with it the step that consumed the branch."""
    if parent_info is not None:
        return _collapse_into_the_parent(graph, target, parent_info)
    to_delete = set(subtree_ids(target.id, graph.steps))
    _drop(graph, to_delete)
    _settle(graph)
    return ApplyResult(
        description=f"Deleted {target.id} and subtree",
        dropped_step_ids=sorted(to_delete),
    )


def _collapse_combine(
    graph: StrategyGraph,
    target: StrategyStep,
    parent_info: tuple[StrategyStep, str] | None,
) -> ApplyResult:
    if parent_info is None:
        return _promote_primary(graph, target, None)
    return _collapse_into_the_parent(graph, target, parent_info)


def _collapse_into_the_parent(
    graph: StrategyGraph,
    target: StrategyStep,
    parent_info: tuple[StrategyStep, str],
) -> ApplyResult:
    """The branch goes, and the step that read it goes with it.

    A transform with no input reads nothing and a combine with one branch
    combines nothing, so the parent leaves too. A combine's other branch takes
    the place the parent held.
    """
    parent, slot = parent_info
    sibling_id = None
    if parent.kind is StepKind.COMBINE:
        sibling_id = (
            parent.secondary_input_id if slot == "primary" else parent.primary_input_id
        )
    to_delete = set(subtree_ids(target.id, graph.steps)) | {parent.id}
    grandparent_info = graph.parent_of(parent.id)
    if grandparent_info is not None:
        grandparent, gp_slot = grandparent_info
        _set_input_slot(grandparent, gp_slot, sibling_id)
    _drop(graph, to_delete)
    _settle(graph)
    return ApplyResult(
        description=f"Collapsed {parent.id}",
        dropped_step_ids=sorted(to_delete),
    )


def _orphan_sibling(
    graph: StrategyGraph,
    target: StrategyStep,
    parent: StrategyStep,
    slot: str,
) -> ApplyResult:
    """Delete this branch and detach the combine and its other input.

    The survivors form their own component. WDK rejects a step that has inputs
    but no strategy, so a detached component stays local.
    """
    to_delete = set(subtree_ids(target.id, graph.steps))
    _drop(graph, to_delete)
    _demote_to_single_input(parent, slot)

    grandparent_info = graph.parent_of(parent.id)
    if grandparent_info is not None:
        grandparent, gp_slot = grandparent_info
        _demote_to_single_input(grandparent, gp_slot)

    _settle(graph)
    return ApplyResult(
        description=f"Deleted {target.id}, orphaned {parent.id}",
        dropped_step_ids=sorted(to_delete),
    )


def _promote_primary(
    graph: StrategyGraph,
    target: StrategyStep,
    parent_info: tuple[StrategyStep, str] | None,
) -> ApplyResult:
    """The step goes and the step it reads stands where it stood.

    A secondary branch feeds only the step that is going, so it leaves with
    it. This is the re-wiring WDK performs when a strategy loses its root.
    """
    secondary_id = target.secondary_input_id
    to_delete = {target.id}
    if secondary_id is not None:
        to_delete |= set(subtree_ids(secondary_id, graph.steps))
    primary_id = target.primary_input_id
    if parent_info is not None:
        parent, slot = parent_info
        _set_input_slot(parent, slot, primary_id)
    _drop(graph, to_delete)
    _settle(graph, primary_id)
    return ApplyResult(
        description=f"Promoted primary of {target.id}",
        dropped_step_ids=sorted(to_delete),
    )


def _apply_delete_edge(graph: StrategyGraph, op: DeleteEdgeOp) -> ApplyResult:
    target = _require(graph, op.target_id, "step")

    if op.resolution == DeleteEdgeResolution.COLLAPSE:
        return _apply_delete_step(
            graph,
            DeleteStepOp(
                step_id=op.source_id,
                resolution=DeleteResolution.COLLAPSE_COMBINE,
            ),
        )

    wired = (
        target.primary_input_id if op.slot == "primary" else target.secondary_input_id
    )
    if wired != op.source_id:
        msg = (
            f"{op.slot} input of {op.target_id!r} is not wired to {op.source_id!r}; "
            f"the graph changed since this edge was drawn"
        )
        raise ApplyError(msg)

    _demote_to_single_input(target, op.slot)
    _settle(graph, op.target_id)
    return ApplyResult(description=f"Detached edge {op.source_id} to {op.target_id}")
