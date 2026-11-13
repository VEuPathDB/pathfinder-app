"""Health-check probes for external dependencies."""

from assistant_core.platform.logging import get_logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

WORKER_HEARTBEAT_MAX_AGE_SECONDS = 30.0


async def check_database(session: AsyncSession) -> bool:
    """Return ``True`` if the database responds to a simple query."""
    await session.execute(text("SELECT 1"))
    return True


async def worker_is_alive(
    session: AsyncSession,
    *,
    max_age_seconds: float = WORKER_HEARTBEAT_MAX_AGE_SECONDS,
) -> bool:
    """True if a Procrastinate worker reported a heartbeat within the window.

    Matches Procrastinate's own ``stalled_worker_timeout`` default (30s, with
    a 10s heartbeat interval), so a worker counts as alive here until
    Procrastinate itself would prune it.
    """
    result = await session.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM procrastinate_workers "
            "WHERE last_heartbeat > now() - make_interval(secs => :s))"
        ),
        {"s": max_age_seconds},
    )
    return bool(result.scalar_one())
