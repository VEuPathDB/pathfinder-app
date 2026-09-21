"""Result counts from WDK: one bound criterion, and a whole plan.

The counting itself is the library's; this module holds the session
bookkeeping around it, the budget one criterion reads under, and the name a
plan count writes.
"""

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping

from cachetools import LRUCache
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import StrategyAst
from veupathdb_mcp.wdk import compute_plan_step_counts, count_search_answer

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.platform.identity import STEP_COUNTS_STRATEGY_NAME
from pathfinder.services.strategies.sync_state import WDKSyncState

_STEP_COUNTS_CACHE: LRUCache[str, dict[str, int | None]] = LRUCache(maxsize=20)

# The count informs a binding and never gates one, so it expires rather than
# hold the bind open. The budget sits above every measured read of this shape
# and well under the client's own per-component timeout.
COUNT_BUDGET_SECONDS = 5.0


async def count_bound_criterion(
    site_id: str,
    record_type: str,
    search_name: str,
    params: Mapping[str, ParamValue],
) -> int | None:
    """The records the bound search answers, or None when no count arrives."""
    return await count_search_answer(
        site_id,
        record_type,
        search_name,
        params,
        timeout_seconds=COUNT_BUDGET_SECONDS,
    )


def _the_step_and_what_reads_it(graph: StrategyGraph, step_id: str) -> Iterator[str]:
    """The step, and every combine that takes it as an input, up to the root."""
    current: str | None = step_id
    seen: set[str] = set()
    while current is not None and current not in seen:
        seen.add(current)
        yield current
        parent = graph.parent_of(current)
        current = None if parent is None else parent[0].id


def invalidate_counts_for(
    sync_state: WDKSyncState,
    step_ids: Iterable[str],
    *,
    graph: StrategyGraph,
) -> None:
    """Mark the cached counts of ``step_ids`` and of their ancestors unknown.

    A combine answers over its inputs, so a step whose search changed takes
    every step above it with it. ``None`` means the count must be recomputed.
    A stale integer reads as fact.
    """
    for step_id in step_ids:
        for affected in _the_step_and_what_reads_it(graph, step_id):
            if affected in sync_state.step_counts:
                sync_state.step_counts[affected] = None


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
