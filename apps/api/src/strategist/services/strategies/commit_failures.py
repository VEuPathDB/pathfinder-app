from collections.abc import Sequence
from enum import StrEnum

from veupathdb.domain.strategy import (
    StepFilter,
    StepSettings,
    StrategyStep,
    StrategyStepNode,
    settings_of,
    wdk_search_name,
)
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import get_site

from strategist.domain.strategy.build_outcome import StepPushFailure
from strategist.domain.strategy.site_held_settings import SITE_HELD_SETTINGS
from strategist.services.site_errors import site_words


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
