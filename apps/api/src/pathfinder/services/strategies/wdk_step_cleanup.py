import asyncio

from assistant_core.platform.logging import get_logger

from pathfinder.integrations.veupathdb.strategy_api import StrategyAPI
from pathfinder.platform.errors import AppError

logger = get_logger(__name__)


async def delete_orphaned_wdk_steps(
    api: StrategyAPI,
    wdk_step_ids: list[int],
) -> list[int]:
    """Delete orphaned WDK step rows in parallel. Returns ids that failed.

    Tolerates per-step failures: a transient DELETE failure should not abort
    the surrounding commit pipeline. The caller decides how to surface
    leftovers.
    """
    if not wdk_step_ids:
        return []

    async def _one(step_id: int) -> int | None:
        try:
            await api.delete_step(step_id)
        except AppError as exc:
            logger.warning(
                "Failed to delete orphaned WDK step",
                step_id=step_id,
                error=str(exc),
            )
            return step_id
        return None

    results = await asyncio.gather(*(_one(sid) for sid in wdk_step_ids))
    return [sid for sid in results if sid is not None]
