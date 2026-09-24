"""The count each step of a strategy holds on the site now, in one read."""

from __future__ import annotations

from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import get_strategy_api

logger = get_logger(__name__)


class SiteCounts(CamelModel):
    """The root the site holds and each step's size, by WDK step id.

    A size is None where the site has not computed it.
    """

    model_config = ConfigDict(frozen=True)

    root_step_id: int
    counts: dict[int, int | None]


async def read_step_counts(site_id: str, wdk_strategy_id: int) -> SiteCounts | None:
    """One read of the strategy, or None when the site does not answer it."""
    try:
        details = await get_strategy_api(site_id).get_strategy(wdk_strategy_id)
    except VEuPathDBError as exc:
        logger.warning(
            "The site did not answer the count read",
            site_id=site_id,
            wdk_strategy_id=wdk_strategy_id,
            error=str(exc),
        )
        return None
    return SiteCounts(
        root_step_id=details.root_step_id,
        counts={step.id: step.estimated_size for step in details.steps.values()},
    )
