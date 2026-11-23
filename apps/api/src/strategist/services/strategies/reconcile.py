"""What WDK holds for each step a strategy maps, read before a commit plans."""

from collections.abc import Container, Mapping
from http import HTTPStatus
from typing import Protocol

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
    WDKStep,
    WDKStrategyDetails,
    walk_wdk_step_tree,
)
from veupathdb_mcp.wdk import WireStep, build_snapshot_from_wdk

from strategist.services.strategies.sync_state import WDKSyncState

logger = get_logger(__name__)


class StrategyReads(Protocol):
    async def get_strategy(self, strategy_id: int) -> WDKStrategyDetails: ...
    async def find_step(self, step_id: int) -> WDKStep: ...


async def reconcile_sync_state_with_wdk(
    sync_state: WDKSyncState, api: StrategyReads
) -> dict[str, StepSettings]:
    """Read what WDK holds for every mapped step before a commit plans.

    A step WDK no longer holds is unmapped. A step outside the live tree that
    WDK still holds stays mapped and is read on its own. A read that fails
    raises, so no commit plans against settings it did not read.
    """
    if not sync_state.wdk_step_ids:
        return {}
    live_ids: set[int] = set()
    held: dict[str, StepSettings] = {}
    if sync_state.wdk_strategy_id is not None:
        detail = await api.get_strategy(sync_state.wdk_strategy_id)
        sync_state.wdk_strategy_name = detail.name
        sync_state.wdk_strategy_description = detail.description
        held = _held_in(detail, sync_state)
        live_ids = {node.step_id for node in walk_wdk_step_tree(detail.step_tree)}
    dropped: set[str] = set()
    for local, wdk in sync_state.wdk_step_ids.items():
        if wdk in live_ids:
            continue
        step = await _the_step_wdk_holds(api, wdk)
        if step is None:
            dropped.add(local)
        else:
            held[local] = _settings_of_a_step(step)
    if not dropped:
        return held
    sync_state.wdk_step_ids = {
        local: wdk
        for local, wdk in sync_state.wdk_step_ids.items()
        if local not in dropped
    }
    logger.info("Reconciled sync_state against WDK", dropped=sorted(dropped))
    return held


async def _the_step_wdk_holds(api: StrategyReads, wdk_step_id: int) -> WDKStep | None:
    try:
        return await api.find_step(wdk_step_id)
    except VEuPathDBError as exc:
        if exc.status == HTTPStatus.NOT_FOUND:
            return None
        raise


def _settings_of_a_step(step: WDKStep) -> StepSettings:
    config = step.search_config
    return StepSettings(
        search_name=step.search_name,
        parameters={
            name: HeldValue(wire=value) for name, value in config.parameters.items()
        },
        filters=[
            StepFilter.model_validate(f.model_dump(by_alias=True, mode="json"))
            for f in config.filters
        ],
        wdk_weight=config.wdk_weight,
    )


def held_by_id(
    live: WDKStrategyDetails | None, sync_state: WDKSyncState
) -> dict[str, StepSettings]:
    if live is None:
        return {}
    try:
        return _held_in(live, sync_state)
    except VEuPathDBError as exc:
        logger.warning("The held strategy did not read back", error=str(exc))
        return {}


def _held_in(
    live: WDKStrategyDetails, sync_state: WDKSyncState
) -> dict[str, StepSettings]:
    snapshot, wire = build_snapshot_from_wdk(live)
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
    held: Mapping[str, StepSettings],
    *,
    unfinished: Container[str],
) -> dict[str, StepSettings]:
    nodes = (
        []
        if old is None
        else [*walk(old.root), *(n for r in old.detached_roots for n in walk(r))]
    )
    for node in nodes:
        step = steps.get(node.id)
        if step is not None and step.filters_wdk_added is None:
            step.filters_wdk_added = node.filters_wdk_added
    was_stated = {node.id: set(node.parameters) for node in nodes}
    filtered = {node.id: {f.name for f in node.filters} for node in nodes}
    for node in walk(root):
        step = steps[node.id]
        if (
            node.id in held
            and node.id not in unfinished
            and step.filters_wdk_added is None
        ):
            named = filtered.get(node.id, set()) | {f.name for f in node.filters}
            step.filters_wdk_added = [
                f for f in held[node.id].filters if f.name not in named
            ]
    return {
        node.id: _as_planned(
            held[node.id],
            settings_of(node),
            steps[node.id].filters_wdk_added or [],
            stated_before=was_stated.get(node.id, set()),
        )
        for node in walk(root)
        if node.id in held
    }


def _as_planned(
    holds: StepSettings,
    plan: StepSettings,
    wdk_added: list[StepFilter],
    *,
    stated_before: set[str],
) -> StepSettings:
    stated = {f.name for f in plan.filters}
    named = plan.parameters.keys() | stated_before
    return holds.model_copy(
        update={
            "parameters": {k: v for k, v in holds.parameters.items() if k in named},
            "filters": [
                f for f in holds.filters if f.name in stated or f not in wdk_added
            ],
            "expanded_strategy_id": plan.expanded_strategy_id,
            "expanded_name": plan.expanded_name or holds.expanded_name,
        }
    )


def learn_what_wdk_added(
    step: StrategyStep,
    node: StrategyStepNode,
    holds: StepSettings | None,
    before: StepSettings | None,
) -> None:
    if holds is None:
        return
    if step.filters_wdk_added is None:
        step.filters_wdk_added = holds.filters_wdk_added(settings_of(node))
        return
    known = {f.name for f in step.filters_wdk_added}
    stated = {f.name for f in node.filters}
    dropped = {
        f.name for f in (before or StepSettings()).filters if f.name not in stated
    }
    step.filters_wdk_added += [f for f in holds.filters if f.name in dropped - known]
