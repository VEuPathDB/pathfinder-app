"""Pushes local graph state to WDK: step tree, strategy, counts, decorations."""

from dataclasses import dataclass

from assistant_core.platform.logging import get_logger

from pathfinder.domain.strategy.ast import StrategyStepNode
from pathfinder.domain.strategy.graph_model import (
    pushable_root_id,
    rebuild_tree,
    record_class_of,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.tree import fold, walk
from pathfinder.domain.strategy.validate import validate_strategy
from pathfinder.domain.strategy.validation import StepValidation
from pathfinder.integrations.veupathdb.factory import get_site, get_strategy_api
from pathfinder.integrations.veupathdb.strategy_api import StrategyAPI
from pathfinder.integrations.veupathdb.wdk_models import (
    WDKStepTree,
    WDKStrategyDetails,
)
from pathfinder.platform.errors import AppError, StrategyCompilationError
from pathfinder.services.catalog.searches import (
    assign_step_record_classes,
    make_record_type_resolver,
)
from pathfinder.services.strategies.build import RootResolutionError, resolve_root_step
from pathfinder.services.strategies.sync_state import WDKSyncState

logger = get_logger(__name__)


@dataclass
class SyncResult:
    """Outcome of a successful strategy sync."""

    wdk_strategy_id: int | None
    wdk_url: str | None
    root_step_id: int
    counts: dict[str, int | None]
    root_count: int | None
    zero_step_ids: list[str]
    step_count: int


def build_step_tree_from_graph(
    root: StrategyStepNode,
    wdk_step_ids: dict[str, int],
) -> WDKStepTree:
    """Build a WDK step tree, replacing local step IDs with WDK step IDs.

    :raises StrategyCompilationError: If any step in the tree lacks a WDK step ID.
    """

    def node(step: StrategyStepNode, inputs: list[WDKStepTree]) -> WDKStepTree:
        wdk_id = wdk_step_ids.get(step.id)
        if wdk_id is None:
            msg = f"Step '{step.id}' has no WDK step ID -- was it pushed to WDK?"
            raise StrategyCompilationError(msg)
        slots: list[WDKStepTree | None] = [*inputs, None, None]
        return WDKStepTree(
            step_id=wdk_id, primary_input=slots[0], secondary_input=slots[1]
        )

    return fold(root, node)


def _extract_counts_and_validations(
    strategy_info: WDKStrategyDetails,
    wdk_step_ids: dict[str, int],
) -> tuple[dict[str, int | None], dict[str, StepValidation], int | None]:
    """Extract per-step counts and validations, keyed by local step ID.

    :returns: Tuple of (counts, validations, root_count).
    """
    counts: dict[str, int | None] = {}
    validations: dict[str, StepValidation] = {}
    root_count: int | None = None

    wdk_to_local = {v: k for k, v in wdk_step_ids.items()}

    for wdk_id_str, wdk_step in strategy_info.steps.items():
        try:
            wdk_id = int(wdk_id_str)
        except ValueError, TypeError:
            continue
        local_id = wdk_to_local.get(wdk_id)
        if local_id:
            counts[local_id] = wdk_step.estimated_size
            if wdk_step.validation is not None:
                validations[local_id] = wdk_step.validation

    root_local = wdk_to_local.get(strategy_info.root_step_id)
    if root_local:
        root_count = counts.get(root_local)

    return counts, validations, root_count


async def _apply_decorations(
    root_step: StrategyStepNode,
    wdk_step_ids: dict[str, int],
    api: StrategyAPI,
) -> None:
    """Apply declared filters, analyses, and reports to each WDK step."""
    for step in walk(root_step):
        wdk_step_id = wdk_step_ids.get(step.id)
        if wdk_step_id is None:
            continue
        for step_filter in step.filters:
            await api.set_step_filter(
                step_id=wdk_step_id,
                filter_name=step_filter.name,
                value=step_filter.value,
                disabled=step_filter.disabled,
            )
        for analysis in step.analyses:
            await api.run_step_analysis(
                step_id=wdk_step_id,
                analysis_type=analysis.analysis_type,
                parameters=analysis.parameters,
                custom_name=analysis.custom_name,
            )
        for report in step.reports:
            await api.run_step_report(
                step_id=wdk_step_id,
                report_name=report.report_name,
                config=report.config,
            )


async def _create_or_update_wdk_strategy(
    api: StrategyAPI,
    step_tree: WDKStepTree,
    name: str,
    sync_state: WDKSyncState,
) -> int:
    """Create a new WDK strategy, or update the existing one.

    A failed update creates a new strategy instead.

    :returns: The WDK strategy ID.
    """
    wdk_strategy_id = sync_state.wdk_strategy_id

    if wdk_strategy_id is None:
        result = await api.create_strategy(step_tree, name)
        logger.info("Created WDK strategy", wdk_strategy_id=result.id)
        return result.id

    if step_tree != sync_state.wdk_step_tree:
        try:
            await api.update_strategy(
                strategy_id=wdk_strategy_id,
                step_tree=step_tree,
                name=name,
            )
        except AppError as update_err:
            logger.warning(
                "Failed to update WDK strategy, creating new",
                wdk_strategy_id=wdk_strategy_id,
                error=str(update_err),
            )
            result = await api.create_strategy(step_tree, name)
            return result.id
        else:
            logger.info(
                "Updated WDK strategy step tree",
                wdk_strategy_id=wdk_strategy_id,
            )
            return wdk_strategy_id

    logger.debug(
        "Step tree unchanged, skipping WDK update",
        wdk_strategy_id=wdk_strategy_id,
    )
    return wdk_strategy_id


async def _fetch_strategy_state(
    api: StrategyAPI,
    wdk_strategy_id: int,
    wdk_step_ids: dict[str, int],
    step_tree: WDKStepTree,
) -> tuple[dict[str, int | None], dict[str, StepValidation], int | None, int]:
    """Fetch strategy details.

    :returns: Tuple of (counts, validations, root_count, root_wdk_step_id).
    """
    try:
        strategy_info = await api.get_strategy(wdk_strategy_id)
    except AppError as e:
        logger.warning("Strategy count lookup failed", error=str(e))
        return {}, {}, None, step_tree.step_id
    else:
        counts, validations, root_count = _extract_counts_and_validations(
            strategy_info, wdk_step_ids
        )
        return counts, validations, root_count, strategy_info.root_step_id


async def sync_strategy_for_site(
    *,
    graph: StrategyGraph,
    sync_state: WDKSyncState,
    site_id: str,
    strategy_name: str | None = None,
) -> SyncResult:
    """Sync graph state to WDK: build step tree, create or update strategy, fetch counts.

    Every step must already hold a WDK step ID.

    :raises RootResolutionError: If root step cannot be determined.
    :raises StrategyCompilationError: If steps lack WDK IDs or validation fails.
    :raises AppError: On WDK API failures.
    """
    api = get_strategy_api(site_id)
    root = resolve_root_step(graph, None)
    # A combine step that lacks an input is not computable. WDK receives the
    # surviving branch instead.
    pushable_id = pushable_root_id(root.id, graph.steps)
    if pushable_id is None:
        msg = "No computable step in graph. Finish wiring the strategy first."
        raise RootResolutionError(msg)
    root_step = rebuild_tree(pushable_id, graph.steps)

    if any(step.search_name and not step.record_class for step in graph.steps.values()):
        resolver = await make_record_type_resolver(site_id)
        await assign_step_record_classes(graph.steps, resolver)
    graph.record_type = record_class_of(
        pushable_id, graph.steps, fallback=graph.record_type or "transcript"
    )

    _validate_graph(root_step, graph.record_type)

    step_tree = build_step_tree_from_graph(root_step, sync_state.wdk_step_ids)

    name = strategy_name or graph.name or "Untitled Strategy"
    wdk_strategy_id = await _create_or_update_wdk_strategy(
        api, step_tree, name, sync_state
    )

    counts, validations, root_count, root_wdk_step_id = await _fetch_strategy_state(
        api, wdk_strategy_id, sync_state.wdk_step_ids, step_tree
    )

    await _maybe_apply_decorations(root_step, sync_state.wdk_step_ids, api)

    sync_state.wdk_strategy_id = wdk_strategy_id
    sync_state.wdk_step_tree = step_tree
    sync_state.step_counts = counts
    sync_state.step_validations = validations

    all_steps = walk(root_step)
    wdk_url = get_site(site_id).strategy_url(wdk_strategy_id, root_wdk_step_id)
    zeros = sorted([sid for sid, c in counts.items() if c == 0])

    return SyncResult(
        wdk_strategy_id=wdk_strategy_id,
        wdk_url=wdk_url,
        root_step_id=root_wdk_step_id,
        counts=counts,
        root_count=root_count,
        zero_step_ids=zeros,
        step_count=len(all_steps),
    )


def _validate_graph(root_step: StrategyStepNode, record_type: str | None) -> None:
    """Validate the strategy structure when a record type is known."""
    if not record_type:
        return
    validation_result = validate_strategy(root_step, record_type)
    if not validation_result.valid:
        errors = [
            {"path": e.path, "message": e.message} for e in validation_result.errors
        ]
        msg = f"Strategy validation failed: {errors}"
        raise StrategyCompilationError(msg)


async def _maybe_apply_decorations(
    root_step: StrategyStepNode,
    wdk_step_ids: dict[str, int],
    api: StrategyAPI,
) -> None:
    """Apply step decorations when at least one step declares them."""
    all_steps = walk(root_step)
    has_decorations = any(
        step.filters or step.analyses or step.reports for step in all_steps
    )
    if not has_decorations:
        return
    try:
        await _apply_decorations(root_step, wdk_step_ids, api)
    except AppError as e:
        logger.warning("Step decoration failed (non-fatal)", error=str(e))
