"""The strategy as the site holds it now, and each step's count, in one read."""

from __future__ import annotations

from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import WDKStrategyDetails, get_strategy_api

from pathfinder.services.strategies.strategy_line import held_strategy

logger = get_logger(__name__)


class SiteCounts(CamelModel):
    """The root the site holds and each step's size, by WDK step id.

    A size is None where the site has not computed it.
    """

    model_config = ConfigDict(frozen=True)

    root_step_id: int
    counts: dict[int, int | None]


async def read_site_strategy(
    site_id: str, wdk_strategy_id: int
) -> WDKStrategyDetails | None:
    try:
        async with held_strategy(site_id, wdk_strategy_id):
            return await get_strategy_api(site_id).get_strategy(wdk_strategy_id)
    except VEuPathDBError as exc:
        logger.warning(
            "The site did not answer the strategy read",
            site_id=site_id,
            wdk_strategy_id=wdk_strategy_id,
            error=str(exc),
        )
        return None


async def read_step_counts(site_id: str, wdk_strategy_id: int) -> SiteCounts | None:
    details = await read_site_strategy(site_id, wdk_strategy_id)
    if details is None:
        return None
    return SiteCounts(
        root_step_id=details.root_step_id,
        counts={step.id: step.estimated_size for step in details.steps.values()},
    )
