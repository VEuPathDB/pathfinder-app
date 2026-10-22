"""Periodic sweeper that deletes expired export rows."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from sqlalchemy import delete

from pathfinder.persistence.models import Export
from pathfinder.persistence.rows import rows_changed

logger = get_logger(__name__)

SWEEP_INTERVAL_SECONDS: int = 5 * 60


async def sweep_expired_exports() -> int:
    """Delete expired export rows. Returns the number deleted."""
    async with async_session_factory() as session:
        result = await session.execute(
            delete(Export).where(Export.expires_at < datetime.now(UTC))
        )
        await session.commit()
        return rows_changed(result)


async def run_sweeper_loop() -> None:
    """Long-running coroutine. The caller spawns it."""
    while True:
        try:
            n = await sweep_expired_exports()
            if n:
                logger.info("Swept %d expired export rows", n)
        except Exception:
            logger.exception("Export sweeper iteration failed")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
