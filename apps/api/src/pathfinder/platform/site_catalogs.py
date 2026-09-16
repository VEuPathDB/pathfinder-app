"""The warm-up's per-site catalog preload and the retry that follows it.

Each site gets its own budget and its own outcome, so a site that does not
answer is degraded on its own and the process keeps serving the rest.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable

from assistant_core.platform.logging import get_logger
from veupathdb.errors import VEuPathDBError

from pathfinder.platform.readiness import ReadinessState

logger = get_logger(__name__)

CatalogLoader = Callable[[str], Awaitable[object]]
Sleeper = Callable[[float], Awaitable[None]]


async def _load_one(
    loader: CatalogLoader,
    site_id: str,
    readiness: ReadinessState,
    budget_seconds: float,
) -> None:
    try:
        async with asyncio.timeout(budget_seconds):
            await loader(site_id)
    # A budget stop raises TimeoutError, which is an OSError.
    except (VEuPathDBError, OSError, RuntimeError) as e:
        logger.warning(
            "[warm-up] Site catalog did not load",
            site_id=site_id,
            error_class=type(e).__name__,
        )
        readiness.mark_catalog_failed(site_id, e)
    else:
        readiness.mark_catalog_ready(site_id)


async def preload_catalogs(
    *,
    loader: CatalogLoader,
    site_ids: Iterable[str],
    readiness: ReadinessState,
    budget_seconds: float,
) -> None:
    """Load every site's catalog at once, each inside its own budget."""
    sites = list(site_ids)
    for site_id in sites:
        readiness.register_catalog(site_id)
    await asyncio.gather(
        *(_load_one(loader, site_id, readiness, budget_seconds) for site_id in sites)
    )


async def retry_degraded_catalogs(
    *,
    loader: CatalogLoader,
    readiness: ReadinessState,
    budget_seconds: float,
) -> None:
    """Reload the sites whose catalog is not ready, one at a time."""
    for site_id in readiness.degraded:
        await _load_one(loader, site_id, readiness, budget_seconds)


async def run_catalog_retry_loop(
    *,
    loader: CatalogLoader,
    readiness: ReadinessState,
    budget_seconds: float,
    interval_seconds: float,
    sleep: Sleeper = asyncio.sleep,
) -> None:
    """Retry every degraded site on an interval, until the lifespan ends."""
    while True:
        await sleep(interval_seconds)
        await retry_degraded_catalogs(
            loader=loader,
            readiness=readiness,
            budget_seconds=budget_seconds,
        )
