"""Save a subtree of the active strategy as a new WDK saved strategy.

Flow:
1. Find the source step in the active graph by local id.
2. Deep-clone the subtree, assigning fresh local ids (so the clones do not
   collide with the source graph if the user later inserts the saved
   strategy back into the same conversation).
3. Commit the clone through the one commit path with a fresh
   ``WDKSyncState`` as a new saved strategy: it owns its own steps.
4. Return the saved strategy id, name, and url. The caller stores the id
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
)
from veupathdb.errors import ValidationError

from strategist.domain.strategy.session import StrategySession
from strategist.platform.errors import ErrorCode, NotFoundError
from strategist.services.strategies.commit_tree import CommitTarget, commit_tree
from strategist.services.strategies.sync_state import WDKSyncState

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
    sync_state = WDKSyncState()
    committed = await commit_tree(
        site_id=site_id,
        steps=cloned_steps,
        root_id=cloned_root.id,
        old=None,
        sync_state=sync_state,
        target=CommitTarget(name=name, description=description or "", role="saved"),
    )
    if committed.sync is None or committed.refused or committed.record_type is None:
        refused = "; ".join(
            f"step {sid!r}: {text}" for sid, text in committed.refused.items()
        )
        raise ValidationError(
            title="failed to clone step into saved strategy",
            detail=refused or "the site did not take the saved strategy",
        )
    identifier = committed.sync

    logger.info(
        "Saved substrategy",
        wdk_strategy_id=identifier.wdk_strategy_id,
        name=name,
        steps=len(cloned_steps),
    )

    return SavedSubstrategyResult(
        wdk_strategy_id=identifier.wdk_strategy_id,
        name=name,
        description=description,
        record_type=committed.record_type,
        root_step_id=identifier.root_step_id,
        cloned_root=cloned_root,
    )
