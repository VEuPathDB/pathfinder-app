"""Per-step result counts from WDK, cached by plan hash.

A leaf-only strategy uses parallel anonymous reports. Any other strategy needs
a temporary WDK strategy.
"""

import asyncio
import hashlib
import json
from collections.abc import Iterable

from assistant_core.platform.logging import get_logger
from assistant_core.platform.types import JSONObject
from cachetools import LRUCache
from veupathdb.domain.parameters.values import ParamValue
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.ops import DEFAULT_COMBINE_OPERATOR, CombineOp
from veupathdb.domain.strategy.strategy_ast import StrategyAst
from veupathdb.domain.strategy.tree import leaves, walk
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk.client import (
    VEuPathDBClient,
)
from veupathdb.wdk.factory import get_strategy_api
from veupathdb.wdk.strategy_api import StrategyAPI
from veupathdb.wdk.value_decoding import encode_params
from veupathdb.wdk.wdk_models import (
    CombinedStepSpec,
    NewStepSpec,
    WDKSearchConfig,
)
from veupathdb_mcp.controls.control_helpers import delete_temp_strategy

from pathfinder.platform.errors import AppError
from pathfinder.services.strategies.sync import build_step_tree_from_graph
from pathfinder.services.strategies.sync_state import WDKSyncState

logger = get_logger(__name__)

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


async def _count_via_anonymous_report(
    client: VEuPathDBClient,
    record_type: str,
    search_name: str,
    parameters: dict[str, ParamValue],
) -> int | None:
    """Get the result count for one search from the anonymous report endpoint.

    A report with ``numRecords: 0`` returns only ``meta.totalCount``, so no
    step or strategy is created. Returns ``None`` on failure.
    """
    config = WDKSearchConfig(parameters=encode_params(parameters))
    report_config: JSONObject = {"pagination": {"offset": 0, "numRecords": 0}}
    try:
        answer = await client.run_search_report(
            record_type, search_name, config, report_config
        )
    except (AppError, VEuPathDBError) as e:
        logger.warning(
            "Anonymous report count failed",
            record_type=record_type,
            search_name=search_name,
            error=str(e),
        )
        return None
    else:
        return answer.meta.records_returned()


def is_leaf_only_plan(root: StrategyStepNode) -> bool:
    """Whether every step in the plan tree is a search step."""
    return len(leaves(root)) == len(walk(root))


async def compute_step_counts_for_plan(
    payload: StrategyAst,
    site_id: str,
) -> dict[str, int | None]:
    """Compute per-step result counts for a strategy plan.

    A leaf-only plan uses parallel anonymous reports. A plan with combines or
    transforms needs a temporary WDK strategy. Results are cached by plan hash.
    """
    cache_key = plan_cache_key(site_id, payload)
    cached: dict[str, int | None] | None = _STEP_COUNTS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    api = get_strategy_api(site_id)

    if is_leaf_only_plan(payload.root):
        counts = await _compute_leaf_counts_parallel(
            api.client, payload.root, payload.record_type
        )
        _cache_counts(cache_key, counts)
        return counts

    counts = await _compute_counts_via_temp_strategy(api, payload, site_id)
    _cache_counts(cache_key, counts)
    return counts


async def _compute_leaf_counts_parallel(
    client: VEuPathDBClient,
    root: StrategyStepNode,
    record_type: str,
) -> dict[str, int | None]:
    """Compute counts for all leaf steps in parallel using anonymous reports."""
    all_steps = walk(root)

    tasks = [
        _count_via_anonymous_report(
            client,
            record_type,
            step.search_name,
            step.parameters,
        )
        for step in all_steps
    ]
    results = await asyncio.gather(*tasks)
    return {step.id: count for step, count in zip(all_steps, results, strict=True)}


async def _create_combine_wdk_step(
    api: StrategyAPI,
    step: StrategyStepNode,
    record_type: str,
    primary_wdk_id: int,
    secondary_wdk_id: int,
) -> int | None:
    """Create a WDK combine or colocation step."""
    if step.operator == CombineOp.COLOCATE:
        coloc = step.colocation_params
        if coloc is None:
            return None
        # The GenesBySpanLogic AnswerParams are blank at creation and WDK wires
        # them from the step tree later.
        result = await api.create_transform_step(
            NewStepSpec(
                search_name="GenesBySpanLogic",
                search_config=WDKSearchConfig(parameters=coloc.to_wdk_params()),
            ),
            input_step_id=primary_wdk_id,
            record_type="transcript",
        )
        return result.id
    result = await api.create_combined_step(
        CombinedStepSpec(
            primary_step_id=primary_wdk_id,
            secondary_step_id=secondary_wdk_id,
            boolean_operator=step.operator or DEFAULT_COMBINE_OPERATOR,
        ),
        record_type=record_type,
    )
    return result.id


async def _create_wdk_step(
    api: StrategyAPI,
    step: StrategyStepNode,
    record_type: str,
    wdk_step_ids: dict[str, int],
) -> int | None:
    """Create a single WDK step and return its WDK ID, or None on failure."""
    kind = step.infer_kind()
    params = encode_params(step.parameters)
    try:
        if kind == "search":
            result = await api.create_step(
                NewStepSpec(
                    search_name=step.search_name,
                    search_config=WDKSearchConfig(parameters=params),
                ),
                record_type=record_type,
            )
            return result.id
        if kind == "transform" and step.primary_input_id:
            input_wdk_id = wdk_step_ids.get(step.primary_input_id)
            if input_wdk_id is None:
                return None
            result = await api.create_transform_step(
                NewStepSpec(
                    search_name=step.search_name,
                    search_config=WDKSearchConfig(parameters=params),
                ),
                input_step_id=input_wdk_id,
                record_type=record_type,
            )
            return result.id
        if kind == "combine" and step.primary_input_id and step.secondary_input_id:
            primary_wdk_id = wdk_step_ids.get(step.primary_input_id)
            secondary_wdk_id = wdk_step_ids.get(step.secondary_input_id)
            if primary_wdk_id is None or secondary_wdk_id is None:
                return None
            return await _create_combine_wdk_step(
                api,
                step,
                record_type,
                primary_wdk_id,
                secondary_wdk_id,
            )
    except (AppError, VEuPathDBError) as exc:
        logger.warning(
            "Failed to create step for count computation",
            step_id=step.id,
            error=str(exc),
        )
    return None


async def _read_counts_from_strategy(
    api: StrategyAPI,
    strategy_id: int,
    all_steps: list[StrategyStepNode],
    wdk_step_ids: dict[str, int],
    counts: dict[str, int | None],
) -> None:
    """Read estimatedSize from a WDK strategy and populate the counts dict."""
    try:
        wdk_strategy = await api.get_strategy(strategy_id)
        for step in all_steps:
            wdk_id = wdk_step_ids.get(step.id)
            if wdk_id is None:
                continue
            wdk_step = wdk_strategy.steps.get(str(wdk_id))
            if wdk_step is not None and wdk_step.estimated_size is not None:
                counts[step.id] = wdk_step.estimated_size
    except (AppError, VEuPathDBError) as e:
        logger.warning("Failed to read counts from strategy payload", error=str(e))


async def _compute_counts_via_temp_strategy(
    api: StrategyAPI,
    payload: StrategyAst,
    site_id: str,
) -> dict[str, int | None]:
    """Compute counts from a temporary WDK strategy.

    The strategy is deleted once its counts are read.
    """
    all_steps = walk(payload.root)

    # Maps a local step id to the WDK step id.
    wdk_step_ids: dict[str, int] = {}
    for step in all_steps:
        wdk_id = await _create_wdk_step(api, step, payload.record_type, wdk_step_ids)
        if wdk_id is not None:
            wdk_step_ids[step.id] = wdk_id

    counts: dict[str, int | None] = {step.id: None for step in all_steps}

    # Every step must exist on WDK before the tree can be built.
    if len(wdk_step_ids) != len(all_steps):
        return counts

    try:
        step_tree = build_step_tree_from_graph(payload.root, wdk_step_ids)
    except AppError, VEuPathDBError:
        return counts

    temp_strategy_id: int | None = None
    try:
        created = await api.create_strategy(
            step_tree=step_tree,
            name="Pathfinder step counts",
            description=None,
            is_internal=True,
        )
        temp_strategy_id = created.id
    except (AppError, VEuPathDBError) as exc:
        logger.exception(
            "Failed to create temporary WDK strategy for step counts",
            error=str(exc),
            site_id=site_id,
            step_count=len(all_steps),
        )

    if temp_strategy_id is not None:
        await _read_counts_from_strategy(
            api, temp_strategy_id, all_steps, wdk_step_ids, counts
        )

    await delete_temp_strategy(api, temp_strategy_id)
    return counts


def _cache_counts(cache_key: str, counts: dict[str, int | None]) -> None:
    """Store counts in the LRU cache."""
    _STEP_COUNTS_CACHE[cache_key] = counts
