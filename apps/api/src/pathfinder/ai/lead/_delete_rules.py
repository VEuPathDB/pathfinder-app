"""Which step a delete may re-wire, how, and the two calls it refuses.

Every delete surface reads these, so the two tools answer one question one
way.
"""

from __future__ import annotations

from enum import StrEnum

from assistant_core.graph.tool_summary import count_noun
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import StepKind, subtree_ids

from pathfinder.domain.strategy.operations.types import DeleteResolution
from pathfinder.domain.strategy.session import StrategyGraph, strategy_root_id
from pathfinder.domain.strategy.types import SyncStateProtocol


def steps_outside_the_strategy(
    graph: StrategyGraph, sync_state: SyncStateProtocol | None
) -> list[str]:
    """Every step the strategy does not reach, oldest id first.

    A thread that holds several roots and whose push named none of them has no
    strategy for a step to be outside of, so it reports nothing.
    """
    root = strategy_root_id(graph, sync_state)
    if root is None:
        return []
    reachable = set(subtree_ids(root, graph.steps))
    return sorted(step_id for step_id in graph.steps if step_id not in reachable)


class DeleteSurface(StrEnum):
    """Which caller asked, because they hold different tools."""

    LEAD = "lead"
    BUILDING = "building"


def _the_way_to_clear(surface: DeleteSurface, whole: str) -> str:
    """How this caller removes the whole thing, since no single delete does."""
    if surface is DeleteSurface.LEAD:
        return f"call clear_strategy to remove the whole {whole}"
    return "stop and report it to the Lead, which can clear the strategy"


def roots_by_size(graph: StrategyGraph) -> str:
    """Every root of the graph with the number of steps it holds, largest first."""
    ranked = sorted(
        ((graph.subtree_size(step_id), step_id) for step_id in graph.roots),
        key=lambda root: (-root[0], root[1]),
    )
    return ", ".join(
        f"{step_id} ({count_noun(size, 'step')})" for size, step_id in ranked
    )


def refuse_a_delete_the_graph_cannot_place(
    graph: StrategyGraph,
    sync_state: SyncStateProtocol | None,
    step_id: str,
    surface: DeleteSurface,
) -> None:
    """Refuse the two deletes whose outcome the graph does not determine."""
    _refuse_an_ambiguous_root(graph, sync_state, step_id, surface)
    _refuse_a_transform_with_no_heir(graph, sync_state, step_id, surface)


def _refuse_an_ambiguous_root(
    graph: StrategyGraph,
    sync_state: SyncStateProtocol | None,
    step_id: str,
    surface: DeleteSurface,
) -> None:
    """A root of a split thread no push named is not known to be the strategy's.

    Size is not identity, so a delete decided on the largest component can
    re-wire the leftover and take the strategy with it. A root that is one
    step takes only itself, so the approval names the whole effect and it
    goes.
    """
    step = graph.steps.get(step_id)
    if step is None or graph.parent_of(step_id) is not None:
        return
    if strategy_root_id(graph, sync_state) is not None:
        return
    if graph.subtree_size(step_id) == 1:
        return
    msg = (
        f"{step_id} is one of the {len(graph.roots)} roots this thread holds, "
        f"and no push says which of them the strategy is: "
        f"{roots_by_size(graph)}. Name a step under the one you mean, or "
        f"{_the_way_to_clear(surface, 'thread')}."
    )
    raise ModelRetry(msg)


def _refuse_a_transform_with_no_heir(
    graph: StrategyGraph,
    sync_state: SyncStateProtocol | None,
    step_id: str,
    surface: DeleteSurface,
) -> None:
    """Refuse a delete of a transform nothing can take the place of.

    A delete promotes a combine's input and never a transform's, so the
    strategy's root transform, and a transform under another transform, would
    take the tree under them with nothing standing where they stood.
    """
    step = graph.steps.get(step_id)
    if step is None or step.kind is not StepKind.TRANSFORM:
        return
    parent = graph.parent_of(step_id)
    if parent is None:
        if step_id != strategy_root_id(graph, sync_state):
            return
        place = "the root"
    elif parent[0].kind is StepKind.TRANSFORM:
        place = f"its place under {parent[0].id}"
    else:
        return
    msg = (
        f"{step_id} is a transform, and no delete gives its input "
        f"{step.primary_input_id} {place}. Delete a step under it, or "
        f"{_the_way_to_clear(surface, 'strategy')}."
    )
    raise ModelRetry(msg)


def delete_resolution(
    graph: StrategyGraph, sync_state: SyncStateProtocol | None, step_id: str
) -> DeleteResolution:
    """How the tree is re-wired once the step goes.

    A combine under a transform leaves with its secondary branch. Any other
    step with a combine above it collapses that combine onto its sibling. The
    strategy's own root collapses onto its primary input when it is a combine,
    and any other root leaves with whatever hangs under it.
    """
    parent = graph.parent_of(step_id)
    step = graph.steps.get(step_id)
    is_combine = step is not None and step.kind is StepKind.COMBINE
    if parent is not None:
        if is_combine and parent[0].kind is StepKind.TRANSFORM:
            return DeleteResolution.PROMOTE_PRIMARY
        return DeleteResolution.COLLAPSE_COMBINE
    if is_combine and step_id == strategy_root_id(graph, sync_state):
        return DeleteResolution.COLLAPSE_COMBINE
    return DeleteResolution.DELETE_SUBTREE
