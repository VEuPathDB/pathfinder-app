"""Per-step counts read from WDK rather than from what a build recorded.

WDK owns the strategy. The graph editor and the site itself both change it
without touching the counts a build wrote, so anything derived from those
counts has to be checked against the server to mean anything.
"""

from __future__ import annotations

from assistant_core.platform.logging import get_logger
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import WDKStrategyDetails, get_strategy_api

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.types import SyncStateProtocol
from pathfinder.services.strategies.sync_state import WDKSyncState

logger = get_logger(__name__)

__all__ = [
    "counts_the_site_holds",
    "read_the_live_strategy",
    "read_wdk_step_counts",
    "replace_counts_with_wdks",
    "take_the_sites_counts",
]


async def read_the_live_strategy(
    sync_state: SyncStateProtocol,
    site_id: str,
) -> WDKStrategyDetails | None:
    """The strategy as the site holds it now, or None when there is none to read.

    An unsynced strategy and a failed read both answer None.
    """
    strategy_id = sync_state.wdk_strategy_id
    if strategy_id is None or not sync_state.wdk_step_ids:
        return None
    try:
        return await get_strategy_api(site_id).get_strategy(strategy_id)
    except VEuPathDBError, OSError:
        logger.warning("Live strategy read failed", strategy_id=strategy_id)
        return None


def counts_the_site_holds(
    live: WDKStrategyDetails, sync_state: SyncStateProtocol
) -> dict[str, int | None]:
    """The count ``live`` answers for each local step, keyed as the graph keys it."""
    sizes = {
        int(wdk_id): step.estimated_size
        for wdk_id, step in live.steps.items()
        if wdk_id.isdigit()
    }
    return {
        local_id: sizes.get(wdk_id)
        for local_id, wdk_id in sync_state.wdk_step_ids.items()
    }


async def read_wdk_step_counts(
    sync_state: SyncStateProtocol,
    site_id: str,
) -> dict[str, int | None]:
    """Return per-local-step counts from WDK, keyed as the graph keys them.

    An empty mapping means "not known", never "nothing changed": an unsynced
    strategy and a failed read both produce it.
    """
    live = await read_the_live_strategy(sync_state, site_id)
    return {} if live is None else counts_the_site_holds(live, sync_state)


def take_the_sites_counts(
    *,
    graph: StrategyGraph,
    sync_state: WDKSyncState,
    live: WDKStrategyDetails,
) -> None:
    """Make the counts in ``live`` the only counts the session holds.

    A local step the site answers no size for becomes unknown.
    """
    counts = counts_the_site_holds(live, sync_state)
    sync_state.step_counts = {step_id: counts.get(step_id) for step_id in graph.steps}


async def replace_counts_with_wdks(
    *,
    graph: StrategyGraph,
    sync_state: WDKSyncState,
    site_id: str,
) -> bool:
    """Make the site's counts the only counts the session holds.

    A read that answers nothing leaves the session as it stands and reports
    False, so a caller that must not confirm the stored numbers can refuse.
    """
    live = await read_the_live_strategy(sync_state, site_id)
    if live is None:
        return False
    take_the_sites_counts(graph=graph, sync_state=sync_state, live=live)
    return True
