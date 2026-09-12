"""The procrastinate worker rows a test needs the readiness probe to see."""

from __future__ import annotations

from assistant_core.platform import db
from sqlalchemy import text

__all__ = ["clear_workers", "insert_worker_heartbeat"]


async def clear_workers() -> None:
    """Leave no worker beating, so the probe reports none alive."""
    async with db.async_session_factory() as session:
        await session.execute(text("DELETE FROM procrastinate_workers"))
        await session.commit()


async def insert_worker_heartbeat(*, age_seconds: float) -> None:
    """Record one worker whose last heartbeat is this old."""
    async with db.async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO procrastinate_workers (last_heartbeat) "
                "VALUES (now() - make_interval(secs => :s))",
            ),
            {"s": age_seconds},
        )
        await session.commit()
