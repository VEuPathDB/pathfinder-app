"""Per-step counts read from WDK rather than from what a build recorded.

WDK owns the strategy. The graph editor and the site itself both change it
without touching the counts a build wrote, so anything derived from those
counts has to be checked against the server to mean anything.
"""

from __future__ import annotations

from assistant_core.platform.logging import get_logger
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk.factory import get_strategy_api

from pathfinder.domain.strategy.types import SyncStateProtocol

logger = get_logger(__name__)

__all__ = ["read_wdk_step_counts"]


async def read_wdk_step_counts(
    sync_state: SyncStateProtocol,
    site_id: str,
) -> dict[str, int | None]:
    """Return per-local-step counts from WDK, keyed as the graph keys them.

    An empty mapping means "not known", never "nothing changed": an unsynced
    strategy and a failed read both produce it.
    """
    strategy_id = sync_state.wdk_strategy_id
    if strategy_id is None or not sync_state.wdk_step_ids:
        return {}

    try:
        details = await get_strategy_api(site_id).get_strategy(strategy_id)
    except VEuPathDBError, OSError:
        logger.warning("Live step count read failed", strategy_id=strategy_id)
        return {}

    sizes = {
        int(wdk_id): step.estimated_size
        for wdk_id, step in details.steps.items()
        if wdk_id.isdigit()
    }
    return {
        local_id: sizes.get(wdk_id)
        for local_id, wdk_id in sync_state.wdk_step_ids.items()
    }
