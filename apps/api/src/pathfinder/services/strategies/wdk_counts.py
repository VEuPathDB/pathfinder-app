"""Per-step result counts from WDK, cached by plan hash.

The counting itself is the library's; this module holds the session
bookkeeping around it and names the strategy a count writes.
"""

import hashlib
import json
from collections.abc import Iterable

from cachetools import LRUCache
from veupathdb.domain.strategy.strategy_ast import StrategyAst
from veupathdb_mcp.wdk.plan_counts import compute_plan_step_counts

from pathfinder.platform.identity import STEP_COUNTS_STRATEGY_NAME
from pathfinder.services.strategies.sync_state import WDKSyncState

_STEP_COUNTS_CACHE: LRUCache[str, dict[str, int | None]] = LRUCache(maxsize=20)


def invalidate_counts_for(sync_state: WDKSyncState, step_ids: Iterable[str]) -> None:
    """Mark the cached counts of ``step_ids`` unknown.

    ``None`` means the count must be recomputed. A stale integer reads as fact.
    """
    for step_id in step_ids:
        if step_id in sync_state.step_counts:
            sync_state.step_counts[step_id] = None


def plan_cache_key(site_id: str, payload: StrategyAst) -> str:
    serialized = json.dumps(
        payload.model_dump(by_alias=True, exclude_none=True, mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    return f"{site_id}:{digest}"


async def compute_step_counts_for_plan(
    payload: StrategyAst,
    site_id: str,
) -> dict[str, int | None]:
    """Per-step result counts for a strategy plan, cached by plan hash."""
    cache_key = plan_cache_key(site_id, payload)
    cached: dict[str, int | None] | None = _STEP_COUNTS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    counts = await compute_plan_step_counts(
        payload,
        site_id,
        strategy_name=STEP_COUNTS_STRATEGY_NAME,
    )
    _STEP_COUNTS_CACHE[cache_key] = counts
    return counts
