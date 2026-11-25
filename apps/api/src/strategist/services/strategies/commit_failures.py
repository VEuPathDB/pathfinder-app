from collections.abc import Sequence
from enum import StrEnum

from veupathdb.domain.strategy import (
    StepFilter,
    StepSettings,
    StrategyAst,
    StrategyStep,
    StrategyStepNode,
    settings_of,
    wdk_search_name,
)
from veupathdb.errors import DataParsingError, VEuPathDBError
from veupathdb.wdk import StrategyAPI, get_site

from strategist.domain.strategy.build_outcome import StepPushFailure
from strategist.domain.strategy.site_held_settings import SITE_HELD_SETTINGS
from strategist.services.site_errors import site_words
from strategist.services.strategies.reconcile import reconcile_sync_state_with_wdk
from strategist.services.strategies.started_plan import mark_unwritten
from strategist.services.strategies.sync_state import WDKSyncState


async def what_wdk_holds(
    api: StrategyAPI,
    site_id: str,
    steps: dict[str, StrategyStep],
    root_id: str,
    old: StrategyAst | None,
    sync_state: WDKSyncState,
) -> dict[str, StepSettings] | StepPushFailure:
    try:
        return await reconcile_sync_state_with_wdk(sync_state, api)
    except DataParsingError as exc:
        what = (
            "answered the read of the strategy with a strategy that does not "
            f"parse: {exc}"
        )
    except (VEuPathDBError, OSError) as exc:
        what = f"did not answer the read of the strategy: {exc}"
    root = steps[root_id]
    site = get_site(site_id).display_name
    failure = StepPushFailure(
        step_id=root.id, search_name=wdk_search_name(root), error=f"{site} {what}"
    )
    mark_unwritten(steps, root_id, old, sync_state, failure.error)
    return failure


def unsorted_failure(
    site_id: str, root: StrategyStep, exc: VEuPathDBError[StrEnum]
) -> StepPushFailure:
    site = get_site(site_id).display_name
    return StepPushFailure(
        step_id=root.id,
        search_name=wdk_search_name(root),
        error=(
            f"{site} did not sort the ranked result by score, so it "
            f"is not ranked: {site_words(exc)}"
        ),
    )


def departures(
    site_id: str,
    node: StrategyStepNode,
    step: StrategyStep,
    holds: StepSettings,
    before: StepSettings,
    wdk_added: Sequence[StepFilter],
) -> list[StepPushFailure]:
    stated = settings_of(node)
    found, wanted = dict(holds), dict(stated)
    site = get_site(site_id).display_name
    return [
        StepPushFailure(
            step_id=node.id,
            search_name=wdk_search_name(step),
            error=f"{site} holds {name} {found[name]} for this step, not {wanted[name]}",
        )
        for name in holds.departures_from(before, stated, wdk_added=wdk_added)
        if name in SITE_HELD_SETTINGS
    ]
