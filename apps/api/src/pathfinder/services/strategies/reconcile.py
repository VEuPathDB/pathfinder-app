"""WDK reconciliation: read live WDK state to self-heal local sync_state.

Local `wdk_step_ids` can drift from WDK reality after a partial push
failure or out-of-band edits on the WDK web UI. Before planning a new
push, intersect locally-tracked IDs with what WDK actually has so the
planner doesn't try to PATCH/RECREATE steps that no longer exist (or
worse, CREATE duplicates of steps it forgot were already pushed).
"""

from assistant_core.platform.logging import get_logger
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import get_strategy_api, walk_wdk_step_tree

from pathfinder.services.strategies.sync_state import WDKSyncState

logger = get_logger(__name__)


async def fetch_wdk_strategy_step_ids(site_id: str, wdk_strategy_id: int) -> set[int]:
    """Return the set of WDK step IDs currently in `wdk_strategy_id`'s tree.

    Raises `VEuPathDBError` if WDK is unreachable; callers decide whether
    that is fatal or merely "skip reconciliation, proceed with stale state".
    """
    api = get_strategy_api(site_id)
    detail = await api.get_strategy(wdk_strategy_id)
    return {node.step_id for node in walk_wdk_step_tree(detail.step_tree)}


async def reconcile_sync_state_with_wdk(
    sync_state: WDKSyncState,
    site_id: str,
    wdk_strategy_id: int | None,
) -> None:
    """Drop locally-tracked wdk_step_ids that are not in WDK's actual tree.

    Self-heals from prior partial-failure corruption and out-of-band
    deletes. If the WDK GET fails (network, 404, etc.) the function logs
    and returns - better to push with possibly-stale state than to fail
    the whole patch because reconciliation could not run.
    """
    if wdk_strategy_id is None or not sync_state.wdk_step_ids:
        return
    try:
        live_ids = await fetch_wdk_strategy_step_ids(site_id, wdk_strategy_id)
    except (VEuPathDBError, OSError) as exc:
        logger.warning(
            "WDK reconciliation read failed; proceeding with stale sync_state",
            wdk_strategy_id=wdk_strategy_id,
            error=str(exc),
        )
        return

    dropped = {
        local: wdk
        for local, wdk in sync_state.wdk_step_ids.items()
        if wdk not in live_ids
    }
    if not dropped:
        return
    sync_state.wdk_step_ids = {
        local: wdk for local, wdk in sync_state.wdk_step_ids.items() if wdk in live_ids
    }
    logger.info(
        "Reconciled sync_state against WDK",
        wdk_strategy_id=wdk_strategy_id,
        dropped=dropped,
    )
