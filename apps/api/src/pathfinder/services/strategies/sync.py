"""Pushes local graph state to WDK: step tree, strategy, counts, decorations."""

from dataclasses import dataclass, field

from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy import (
    StepValidation,
    StrategyStepNode,
    pushable_root_id,
    rebuild_tree,
    record_class_of,
    walk,
)
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import (
    MissingWDKStepIdError,
    StrategyAPI,
    WDKStepTree,
    WDKStrategyDetails,
    build_wdk_step_tree,
    get_site,
    get_strategy_api,
)
from veupathdb_mcp.catalog import assign_step_record_classes, make_record_type_resolver

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.validate import validate_strategy
from pathfinder.platform.errors import StrategyCompilationError
from pathfinder.services.strategies.build import RootResolutionError, resolve_root_step
from pathfinder.services.strategies.naming import name_for_the_push
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
    created_wdk_strategy: bool = False
    """True when this sync minted the WDK strategy, rather than updating one."""
    detached_step_ids: list[str] = field(default_factory=list)
    """Steps the WDK strategy does not list after its step tree was put."""


def build_step_tree_from_graph(
    root: StrategyStepNode,
    wdk_step_ids: dict[str, int],
) -> WDKStepTree:
    """Build a WDK step tree, replacing local step IDs with WDK step IDs.

    :raises StrategyCompilationError: If any step in the tree lacks a WDK step ID.
    """
    try:
        return build_wdk_step_tree(root, wdk_step_ids)
    except MissingWDKStepIdError as exc:
        raise StrategyCompilationError(str(exc)) from exc


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


@dataclass(frozen=True)
class _PushedStrategy:
    """The WDK strategy the push landed in, and whether the push minted it."""

    wdk_strategy_id: int
    created: bool


async def _create_or_update_wdk_strategy(
    api: StrategyAPI,
    step_tree: WDKStepTree,
    name: str,
    sync_state: WDKSyncState,
) -> _PushedStrategy:
    """Create a new WDK strategy, or update the existing one.

    A failed update creates a new strategy instead. An unchanged tree sends
    only a name WDK lags on.
    """
    wdk_strategy_id = sync_state.wdk_strategy_id

    if wdk_strategy_id is None:
        result = await api.create_strategy(step_tree, name)
        sync_state.wdk_strategy_name = name
        logger.info("Created WDK strategy", wdk_strategy_id=result.id)
        return _PushedStrategy(result.id, created=True)

    if step_tree != sync_state.wdk_step_tree:
        try:
            await api.update_strategy(
                strategy_id=wdk_strategy_id,
                step_tree=step_tree,
                name=name,
            )
        except VEuPathDBError as update_err:
            logger.warning(
                "Failed to update WDK strategy, creating new",
                wdk_strategy_id=wdk_strategy_id,
                error=str(update_err),
            )
            result = await api.create_strategy(step_tree, name)
            sync_state.wdk_strategy_name = name
            return _PushedStrategy(result.id, created=True)
        else:
            sync_state.wdk_strategy_name = name
            logger.info(
                "Updated WDK strategy step tree",
                wdk_strategy_id=wdk_strategy_id,
            )
            return _PushedStrategy(wdk_strategy_id, created=False)

    await put_the_strategy_name(api, sync_state, name)
    return _PushedStrategy(wdk_strategy_id, created=False)


async def put_the_strategy_name(
    api: StrategyAPI, sync_state: WDKSyncState, name: str
) -> None:
    """Send the name when the one WDK holds is known and is another.

    A refused name is logged: WDK keeps the name it holds, and the next push
    sends this one again.
    """
    held = sync_state.wdk_strategy_name
    if sync_state.wdk_strategy_id is None or held is None or held == name:
        return
    try:
        await api.update_strategy(sync_state.wdk_strategy_id, name=name)
    except VEuPathDBError as exc:
        logger.warning(
            "WDK did not take the strategy's name",
            wdk_strategy_id=sync_state.wdk_strategy_id,
            error=str(exc),
        )
        return
    sync_state.wdk_strategy_name = name


@dataclass
class _StrategyState:
    """What WDK answers about the strategy that now holds the step tree."""

    counts: dict[str, int | None]
    validations: dict[str, StepValidation]
    root_count: int | None
    root_step_id: int
    was_read: bool


async def _fetch_strategy_state(
    api: StrategyAPI,
    wdk_strategy_id: int,
    wdk_step_ids: dict[str, int],
    step_tree: WDKStepTree,
) -> _StrategyState:
    """Fetch strategy details."""
    try:
        strategy_info = await api.get_strategy(wdk_strategy_id)
    except VEuPathDBError as e:
        logger.warning("Strategy count lookup failed", error=str(e))
        return _StrategyState({}, {}, None, step_tree.step_id, was_read=False)
    else:
        counts, validations, root_count = _extract_counts_and_validations(
            strategy_info, wdk_step_ids
        )
        return _StrategyState(
            counts, validations, root_count, strategy_info.root_step_id, was_read=True
        )


def step_tree_is_current(root_step: StrategyStepNode, sync_state: WDKSyncState) -> bool:
    """True when the WDK strategy already holds the tree this graph maps to.

    The tree is keyed by WDK step ids, so a step recreated under a new id
    moves the tree even when every local id stays the same.
    """
    if sync_state.wdk_strategy_id is None:
        return False
    try:
        step_tree = build_step_tree_from_graph(root_step, sync_state.wdk_step_ids)
    except StrategyCompilationError:
        return False
    return step_tree == sync_state.wdk_step_tree


async def sync_strategy_for_site(
    *,
    graph: StrategyGraph,
    sync_state: WDKSyncState,
    site_id: str,
    strategy_name: str | None = None,
    user_prompt: str = "",
) -> SyncResult:
    """Sync graph state to WDK: build step tree, create or update strategy, fetch counts.

    Every step must already hold a WDK step ID. Without ``strategy_name``, a
    graph that has no name yet is pushed under ``user_prompt``.

    :raises RootResolutionError: If root step cannot be determined.
    :raises StrategyCompilationError: If steps lack WDK IDs or validation fails.
    :raises VEuPathDBError: On WDK API failures.
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

    name = strategy_name or name_for_the_push(graph, user_prompt)
    pushed = await _create_or_update_wdk_strategy(api, step_tree, name, sync_state)
    wdk_strategy_id = pushed.wdk_strategy_id

    # A filter narrows what its step answers, so the read follows it. Reading
    # first records the size the step had without its decorations.
    await _maybe_apply_decorations(root_step, sync_state.wdk_step_ids, api)

    state = await _fetch_strategy_state(
        api, wdk_strategy_id, sync_state.wdk_step_ids, step_tree
    )

    all_steps = walk(root_step)
    detached = _detached(all_steps, state)

    sync_state.wdk_strategy_id = wdk_strategy_id
    # The recorded tree is what the strategy holds. Recording a tree the
    # strategy did not take would stop the next commit from putting it again.
    if not detached:
        sync_state.wdk_step_tree = step_tree
    sync_state.step_counts = state.counts
    sync_state.step_validations = state.validations

    wdk_url = get_site(site_id).strategy_url(wdk_strategy_id, state.root_step_id)
    zeros = sorted([sid for sid, c in state.counts.items() if c == 0])

    return SyncResult(
        wdk_strategy_id=wdk_strategy_id,
        wdk_url=wdk_url,
        root_step_id=state.root_step_id,
        counts=state.counts,
        root_count=state.root_count,
        zero_step_ids=zeros,
        step_count=len(all_steps),
        created_wdk_strategy=pushed.created,
        detached_step_ids=detached,
    )


def _detached(all_steps: list[StrategyStepNode], state: _StrategyState) -> list[str]:
    """The pushed steps the strategy does not list, so they compute nothing."""
    if not state.was_read:
        return []
    return sorted(step.id for step in all_steps if step.id not in state.counts)


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
    except VEuPathDBError as e:
        logger.warning("Step decoration failed (non-fatal)", error=str(e))
