from veupathdb.domain.strategy import (
    StepSettings,
    StrategyStep,
    settings_of,
    wdk_search_name,
)
from veupathdb.errors import DataParsingError, VEuPathDBError
from veupathdb.wdk import StrategyAPI, get_site

from strategist.domain.strategy.build_outcome import StepPushFailure
from strategist.services.strategies.reconcile import (
    WhatWDKHolds,
    reconcile_sync_state_with_wdk,
)
from strategist.services.strategies.site_changes import (
    TheTurnsOwn,
    fold_the_sites_values,
)
from strategist.services.strategies.step_push_planner import turn_moved
from strategist.services.strategies.sync_state import WDKSyncState


def the_turns_own(
    steps: dict[str, StrategyStep], started: dict[str, StepSettings]
) -> TheTurnsOwn:
    names: dict[str, frozenset[str]] = {}
    for step_id, step in steps.items():
        was = started.get(step_id)
        if was is None:
            continue
        names[step_id] = turn_moved(settings_of(step), was)
    return TheTurnsOwn(steps=frozenset(steps.keys() - names.keys()), names=names)


async def what_wdk_holds(
    api: StrategyAPI,
    site_id: str,
    steps: dict[str, StrategyStep],
    root_id: str,
    started: dict[str, StepSettings],
    sync_state: WDKSyncState,
) -> WhatWDKHolds | StepPushFailure:
    """Read what WDK holds before a commit plans, and take onto ``steps`` every
    value the site holds that the commit's plan did not move."""
    try:
        holds = await reconcile_sync_state_with_wdk(sync_state, api)
    except DataParsingError as exc:
        what = (
            "answered the read of the strategy with a strategy that does not "
            f"parse: {exc}"
        )
    except (VEuPathDBError, OSError) as exc:
        what = f"did not answer the read of the strategy: {exc}"
    else:
        if holds.live is not None:
            before = {sid: settings_of(step) for sid, step in steps.items()}
            folded = await fold_the_sites_values(
                steps=steps,
                sync_state=sync_state,
                live=holds.live,
                site_id=site_id,
                own=the_turns_own(steps, started),
            )
            for step_id in folded:
                sync_state.site_fold.setdefault(step_id, before[step_id])
        return holds
    root = steps[root_id]
    site = get_site(site_id).display_name
    return StepPushFailure(
        step_id=root.id, search_name=wdk_search_name(root), error=f"{site} {what}"
    )
