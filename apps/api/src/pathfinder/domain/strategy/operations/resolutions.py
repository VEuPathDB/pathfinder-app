"""Which deletes a step admits, and which deletes the graph cannot place."""

from veupathdb.domain.strategy import StepKind, StrategyStep, subtree_ids

from pathfinder.domain.strategy.operations.types import (
    DeleteResolution,
    DeleteStepOp,
    OperationChoice,
)
from pathfinder.domain.strategy.session import StrategyGraph


def compute_delete_choices(graph: StrategyGraph, step_id: str) -> list[OperationChoice]:
    target = graph.steps.get(step_id)
    if target is None:
        return []
    if len(graph.steps) == 1:
        return _sole_step_choices(step_id)
    # A transform that reads nothing has no input to stand in its place, so the
    # rules for a step without one place it.
    if target.kind is StepKind.TRANSFORM and target.primary_input_id is not None:
        return _transform_choices(step_id)
    parent_info = graph.parent_of(step_id)
    if parent_info is None:
        return _root_choices(graph, target)
    return _child_choices(graph, target, parent_info)


def why_the_graph_refuses_the_delete(
    graph: StrategyGraph, op: DeleteStepOp
) -> str | None:
    """The reason no re-wiring of the graph performs this delete, or None.

    Every delete surface reads this before it applies one, so a request the
    algebra cannot carry out is answered and not raised.
    """
    target = graph.steps.get(op.step_id)
    if target is None:
        return f"{op.step_id} is not a step of this strategy"
    has_parent = graph.parent_of(op.step_id) is not None
    if op.resolution is DeleteResolution.ORPHAN_SIBLING and not has_parent:
        return f"{op.step_id} is a root, so no step above it keeps another branch"
    stands_in = _stands_the_input_in_its_place(op.resolution, has_parent=has_parent)
    if stands_in and target.primary_input_id is None:
        return f"{op.step_id} reads no step that can take its place"
    return None


def _stands_the_input_in_its_place(
    resolution: DeleteResolution, *, has_parent: bool
) -> bool:
    """The deletes that leave the step's own input where the step stood."""
    if resolution is DeleteResolution.PROMOTE_PRIMARY:
        return True
    return resolution is DeleteResolution.COLLAPSE_COMBINE and not has_parent


def _sole_step_choices(step_id: str) -> list[OperationChoice]:
    return [
        OperationChoice(
            resolution=DeleteResolution.DELETE_STRATEGY,
            title="Delete strategy",
            description="This is the only step. Removing it empties the strategy.",
            is_default=True,
            will_delete=[step_id],
        )
    ]


def _transform_choices(step_id: str) -> list[OperationChoice]:
    return [
        OperationChoice(
            resolution=DeleteResolution.PROMOTE_PRIMARY,
            title="Delete this transform",
            description=(
                "The step it consumed becomes the input of the next step downstream."
            ),
            is_default=True,
            will_delete=[step_id],
        )
    ]


def _root_choices(graph: StrategyGraph, target: StrategyStep) -> list[OperationChoice]:
    if target.kind is StepKind.COMBINE:
        secondary_subtree_ids = (
            subtree_ids(target.secondary_input_id, graph.steps)
            if target.secondary_input_id is not None
            else []
        )
        return [
            OperationChoice(
                resolution=DeleteResolution.PROMOTE_PRIMARY,
                title="Keep primary branch only",
                description=(
                    "Drop this combine and the secondary branch; the primary "
                    "branch becomes the new root."
                ),
                is_default=True,
                will_delete=[target.id, *secondary_subtree_ids],
            ),
            OperationChoice(
                resolution=DeleteResolution.DELETE_STRATEGY,
                title="Delete entire strategy",
                description="Remove every step.",
                is_default=False,
                will_delete=sorted(graph.steps.keys()),
            ),
        ]
    return [
        OperationChoice(
            resolution=DeleteResolution.DELETE_STRATEGY,
            title="Delete strategy",
            description="Removing this leaf leaves no steps.",
            is_default=True,
            will_delete=sorted(graph.steps.keys()),
        )
    ]


def _child_choices(
    graph: StrategyGraph,
    target: StrategyStep,
    parent_info: tuple[StrategyStep, str],
) -> list[OperationChoice]:
    parent, _ = parent_info
    branch_ids = sorted(subtree_ids(target.id, graph.steps))
    will_delete = sorted([*branch_ids, parent.id])
    if parent.kind is StepKind.COMBINE:
        return [
            OperationChoice(
                resolution=DeleteResolution.COLLAPSE_COMBINE,
                title="Delete and collapse",
                description=(
                    "Drop this branch and the combine; the other branch reconnects "
                    "upward."
                ),
                is_default=True,
                will_delete=will_delete,
            ),
            OperationChoice(
                resolution=DeleteResolution.DELETE_SUBTREE,
                title="Delete this subtree",
                description=(
                    "Same as the first option for a leaf, but for a multi-step "
                    "branch it removes everything below."
                ),
                is_default=False,
                will_delete=will_delete,
            ),
        ]
    return [
        OperationChoice(
            resolution=DeleteResolution.DELETE_SUBTREE,
            title="Delete this and the transform above it",
            description=(
                "The transform consuming this step has no other input, so it is "
                "removed too."
            ),
            is_default=True,
            will_delete=will_delete,
        )
    ]
