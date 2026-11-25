from collections.abc import Container

from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import (
    StepSettings,
    StrategyAst,
    StrategyStep,
    rebuild_tree,
    settings_of,
    walk,
)

from strategist.services.strategies.stated_sides import unmoved
from strategist.services.strategies.sync_state import WDKSyncState


def started_settings(
    old: StrategyAst | None, unfinished: Container[str]
) -> dict[str, StepSettings]:
    if old is None:
        return {}
    return {
        node.id: settings_of(node)
        for root in (old.root, *old.detached_roots)
        for node in walk(root)
        if node.id not in unfinished
    }


def unstated(
    values: dict[str, ParamValue],
    held: dict[str, ParamValue],
    started: StepSettings | None,
) -> dict[str, ParamValue]:
    kept = {} if started is None else started.parameters
    return {
        **unmoved(values, held),
        **{
            name: held[name]
            for name, value in values.items()
            if name in held and name in kept and kept[name] == value
        },
    }


def mark_unwritten(
    steps: dict[str, StrategyStep],
    root_id: str,
    old: StrategyAst | None,
    sync_state: WDKSyncState,
    error: str,
) -> None:
    started = started_settings(old, ())
    for node in walk(rebuild_tree(root_id, steps)):
        moved = node.id not in started or settings_of(node).changed(started[node.id])
        if node.id in sync_state.wdk_step_ids and moved:
            sync_state.wdk_push_errors[node.id] = error
