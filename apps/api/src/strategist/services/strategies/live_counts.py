"""Per-step counts read from WDK rather than from what a build recorded.

WDK owns the strategy. The graph editor and the site itself both change it
without touching the counts a build wrote, so anything derived from those
counts has to be checked against the server to mean anything.
"""

from __future__ import annotations

from assistant_core.platform.logging import get_logger
from pydantic import BaseModel, ConfigDict
from veupathdb.errors import VEuPathDBError, WDKError
from veupathdb.wdk import WDKStrategyDetails, get_strategy_api

from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.types import SyncStateProtocol
from strategist.domain.unread import Unread
from strategist.services.site_errors import site_words
from strategist.services.strategies.sync_state import WDKSyncState

logger = get_logger(__name__)

_GONE = 404

__all__ = [
    "counts_the_site_holds",
    "read_the_live_strategy",
    "read_wdk_step_counts",
    "replace_counts_with_wdks",
    "take_the_sites_counts",
    "the_site_dropped_the_strategy",
]


async def read_the_live_strategy(
    sync_state: SyncStateProtocol,
    site_id: str,
) -> WDKStrategyDetails | Unread | None:
    """The strategy as the site holds it now, None when there is none to read,
    or why the site did not answer."""
    strategy_id = sync_state.wdk_strategy_id
    if strategy_id is None or not sync_state.wdk_step_ids:
        return None
    try:
        return await get_strategy_api(site_id).get_strategy(strategy_id)
    except (VEuPathDBError, OSError) as exc:
        logger.warning("Live strategy read failed", strategy_id=strategy_id)
        return Unread(
            reason=f"the strategy was not read from the site: {site_words(exc)}"
        )


async def the_site_dropped_the_strategy(
    sync_state: SyncStateProtocol, site_id: str
) -> bool:
    """Whether the site refuses the synced strategy and lists the user's
    strategies without it, which a site that is down cannot do."""
    strategy_id = sync_state.wdk_strategy_id
    if strategy_id is None:
        return False
    api = get_strategy_api(site_id)
    try:
        await api.get_strategy(strategy_id)
    except WDKError as refused:
        if refused.status != _GONE:
            return False
    except VEuPathDBError, OSError:
        return False
    else:
        return False
    try:
        listed = await api.list_strategies()
    except VEuPathDBError, OSError:
        return False
    return all(summary.strategy_id != strategy_id for summary in listed)


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
    match await read_the_live_strategy(sync_state, site_id):
        case WDKStrategyDetails() as live:
            return counts_the_site_holds(live, sync_state)
        case _:
            return {}


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
    match await read_the_live_strategy(sync_state, site_id):
        case WDKStrategyDetails() as live:
            take_the_sites_counts(graph=graph, sync_state=sync_state, live=live)
            return True
        case _:
            return False


class SiteRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    live: WDKStrategyDetails | None = None
    not_read: Unread | None = None


def site_read(read: WDKStrategyDetails | Unread | None) -> SiteRead:
    match read:
        case WDKStrategyDetails():
            return SiteRead(live=read)
        case Unread():
            return SiteRead(not_read=read)
        case _:
            return SiteRead()
