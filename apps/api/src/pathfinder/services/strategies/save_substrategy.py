"""Save a subtree of the active strategy as a new WDK saved strategy.

Flow:
1. Find the source step in the active graph by local id.
2. Deep-clone the subtree, assigning fresh local ids (so the clones do not
   collide with the source graph if the user later inserts the saved
   strategy back into the same conversation).
3. Push every cloned node to WDK with a fresh ``WDKSyncState`` - the
   saved strategy must own its own steps, never share with the source.
4. Build a ``WDKStepTree`` from the new wdk_step_ids and POST it as a new
   strategy with ``isSaved=True``.
5. Return the saved strategy id, name, and url. The caller stores the id
   on the source conversation's ``imported_saved_strategy_ids`` once the
   user inserts the saved strategy via a combine step.
"""

from __future__ import annotations

from dataclasses import dataclass

from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy import (
    StrategyStepNode,
    clone_with_fresh_ids,
    flatten_tree,
    rebuild_tree,
    subtree_ids,
    wdk_search_name,
)
from veupathdb.errors import ValidationError
from veupathdb.wdk import get_strategy_api

from pathfinder.domain.strategy.session import StrategySession
from pathfinder.platform.errors import ErrorCode, NotFoundError
from pathfinder.services.strategies.step_wdk_push import push_step_to_wdk
from pathfinder.services.strategies.sync import build_step_tree_from_graph
from pathfinder.services.strategies.sync_state import WDKSyncState

logger = get_logger(__name__)


@dataclass
class SavedSubstrategyResult:
    wdk_strategy_id: int
    name: str
    description: str | None
    record_type: str
    root_step_id: int
    cloned_root: StrategyStepNode


async def save_subtree_as_strategy(
    *,
    session: StrategySession,
    site_id: str,
    source_step_id: str,
    name: str,
    description: str | None = None,
) -> SavedSubstrategyResult:
    """Clone a subtree, push it to WDK as fresh steps, save as a new strategy.

    :param session: Strategy session hydrated from the source conversation.
    :param site_id: VEuPathDB site id (selects the WDK API).
    :param source_step_id: Local id of the step in the active graph whose
        subtree will be saved.
    :param name: Display name for the saved strategy.
    :param description: Optional description.
    :raises AppError: If the source step is missing, no active graph
        exists, any WDK push fails, or strategy creation fails.
    """
    graph = session.get_graph(None)
    if graph is None:
        raise ValidationError(
            title="no active strategy",
            detail="cannot save a substrategy when the conversation has no strategy",
        )

    source_node = graph.steps.get(source_step_id)
    if source_node is None:
        raise NotFoundError(
            code=ErrorCode.NOT_FOUND,
            title="step not found",
            detail=(
                f"step {source_step_id!r} not found in the active strategy "
                f"(available: {sorted(graph.steps)[:20]})"
            ),
        )

    # deep_clone works on the nested shape, so project this subtree first.
    cloned_root = clone_with_fresh_ids(rebuild_tree(source_step_id, graph.steps))
    cloned_steps = flatten_tree(cloned_root)
    push_order = subtree_ids(cloned_root.id, cloned_steps)

    isolated_sync = WDKSyncState()
    record_type = graph.record_type or "transcript"

    for node in (cloned_steps[sid] for sid in push_order):
        wdk_id, _validation, failure = await push_step_to_wdk(
            sync_state=isolated_sync,
            step=node,
            site_id=site_id,
            record_type=record_type,
            search_name=wdk_search_name(node),
            parameters=dict(node.parameters),
        )
        if failure is not None or wdk_id is None:
            reason = failure.error if failure is not None else "no WDK id returned"
            raise ValidationError(
                title="failed to clone step into saved strategy",
                detail=f"step {node.id!r} ({node.search_name}): {reason}",
            )

    step_tree = build_step_tree_from_graph(cloned_root, isolated_sync.wdk_step_ids)

    api = get_strategy_api(site_id)
    identifier = await api.create_strategy(
        step_tree=step_tree,
        name=name,
        description=description,
        is_saved=True,
    )

    logger.info(
        "Saved substrategy",
        wdk_strategy_id=identifier.id,
        name=name,
        steps=len(cloned_steps),
    )

    return SavedSubstrategyResult(
        wdk_strategy_id=identifier.id,
        name=name,
        description=description,
        record_type=record_type,
        root_step_id=isolated_sync.wdk_step_ids[cloned_root.id],
        cloned_root=cloned_root,
    )
