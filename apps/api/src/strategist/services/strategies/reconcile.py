"""WDK reconciliation: read live WDK state to self-heal local sync_state.

Local `wdk_step_ids` can drift from WDK reality after a partial push
failure or out-of-band edits on the WDK web UI. Before planning a new
push, intersect locally-tracked IDs with what WDK actually has so the
planner doesn't try to PATCH/RECREATE steps that no longer exist (or
worse, CREATE duplicates of steps it forgot were already pushed).
"""

from http import HTTPStatus

from assistant_core.platform.logging import get_logger
from veupathdb.domain.parameters import HeldValue
from veupathdb.domain.strategy import (
    StepFilter,
    StepSettings,
    StrategyAst,
    StrategyStep,
    StrategyStepNode,
    settings_of,
    walk,
)
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import (
    StrategyAPI,
    WDKStrategyDetails,
    get_strategy_api,
    walk_wdk_step_tree,
)
from veupathdb_mcp.wdk import WireStep, build_snapshot_from_wdk

from strategist.services.strategies.sync_state import WDKSyncState

logger = get_logger(__name__)


async def reconcile_sync_state_with_wdk(
    sync_state: WDKSyncState,
    site_id: str,
    wdk_strategy_id: int | None,
) -> None:
    """Drop locally-tracked wdk_step_ids WDK no longer holds.

    A step outside the live tree that WDK still holds stays mapped: a commit
    that stopped before its put made it.

    Self-heals from prior partial-failure corruption and out-of-band
    deletes, and records the name WDK holds. If the WDK GET fails (network,
    404, etc.) the function logs and returns - better to push with
    possibly-stale state than to fail the whole patch because reconciliation
    could not run.
    """
    if wdk_strategy_id is None or not sync_state.wdk_step_ids:
        return
    try:
        api = get_strategy_api(site_id)
        detail = await api.get_strategy(wdk_strategy_id)
    except (VEuPathDBError, OSError) as exc:
        logger.warning(
            "WDK reconciliation read failed; proceeding with stale sync_state",
            wdk_strategy_id=wdk_strategy_id,
            error=str(exc),
        )
        return

    sync_state.wdk_strategy_name = detail.name
    sync_state.wdk_strategy_description = detail.description
    sync_state.wdk_held = held_by_id(detail, sync_state)
    live_ids = {node.step_id for node in walk_wdk_step_tree(detail.step_tree)}
    dropped = {
        local: wdk
        for local, wdk in sync_state.wdk_step_ids.items()
        if wdk not in live_ids and not await _wdk_holds(api, wdk)
    }
    if not dropped:
        return
    sync_state.wdk_step_ids = {
        local: wdk
        for local, wdk in sync_state.wdk_step_ids.items()
        if local not in dropped
    }
    logger.info(
        "Reconciled sync_state against WDK",
        wdk_strategy_id=wdk_strategy_id,
        dropped=dropped,
    )


async def _wdk_holds(api: StrategyAPI, wdk_step_id: int) -> bool:
    try:
        await api.find_step(wdk_step_id)
    except VEuPathDBError as exc:
        return exc.status != HTTPStatus.NOT_FOUND
    except OSError:
        return True
    return True


def held_by_id(
    live: WDKStrategyDetails | None, sync_state: WDKSyncState
) -> dict[str, StepSettings]:
    if live is None:
        return {}
    try:
        snapshot, wire = build_snapshot_from_wdk(live)
    except VEuPathDBError as exc:
        logger.warning("The held strategy did not read back", error=str(exc))
        return {}
    local = {str(wdk): sid for sid, wdk in sync_state.wdk_step_ids.items()}
    return {
        local[node.id]: _with_the_held_values(settings_of(node), wire.get(node.id))
        for node in walk(snapshot.root)
        if node.id in local
    }


def _with_the_held_values(
    settings: StepSettings, wire: WireStep | None
) -> StepSettings:
    if settings.operator is not None or wire is None:
        return settings
    held = {name: HeldValue(wire=value) for name, value in wire.parameters.items()}
    return settings.model_copy(update={"parameters": held})


def held_before_the_commit(
    old: StrategyAst | None,
    root: StrategyStepNode,
    steps: dict[str, StrategyStep],
    sync_state: WDKSyncState,
) -> dict[str, StepSettings]:
    if old is None:
        return {}
    nodes = [*walk(old.root), *(n for r in old.detached_roots for n in walk(r))]
    held = [n for n in nodes if n.id in sync_state.wdk_step_ids]
    for node in held:
        step = steps.get(node.id)
        if step is not None and step.filters_wdk_added is None:
            step.filters_wdk_added = node.filters_wdk_added
    found = {node.id: settings_of(node) for node in held}
    for node in walk(root):
        holds = sync_state.wdk_held.get(node.id)
        if holds is not None and node.id in sync_state.wdk_step_ids:
            added = steps[node.id].filters_wdk_added or []
            found[node.id] = _as_planned(holds, settings_of(node), added)
    return found


def _as_planned(
    holds: StepSettings, plan: StepSettings, wdk_added: list[StepFilter]
) -> StepSettings:
    stated = {f.name for f in plan.filters}
    return holds.model_copy(
        update={
            "parameters": {
                k: v for k, v in holds.parameters.items() if k in plan.parameters
            },
            "filters": [
                f for f in holds.filters if f.name in stated or f not in wdk_added
            ],
            "expanded_strategy_id": plan.expanded_strategy_id,
            "expanded_name": plan.expanded_name or holds.expanded_name,
        }
    )
