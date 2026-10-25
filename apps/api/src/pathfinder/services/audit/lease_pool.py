from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from assistant_core.platform.lease import advisory_lease
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from pathfinder.platform.config import get_settings
from pathfinder.services.audit.queue import audit_lock

__all__ = ["audit_lease", "audit_lease_engine", "close_audit_lease_engine"]


class _AuditLeases:
    engine: AsyncEngine | None = None


def audit_lease_engine() -> AsyncEngine:
    if _AuditLeases.engine is None:
        settings = get_settings()
        _AuditLeases.engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=1,
            max_overflow=settings.audit_concurrency - 1,
        )
    return _AuditLeases.engine


async def close_audit_lease_engine() -> None:
    if _AuditLeases.engine is not None:
        await _AuditLeases.engine.dispose()
        _AuditLeases.engine = None


@asynccontextmanager
async def audit_lease(run_id: UUID) -> AsyncIterator[bool]:
    async with advisory_lease(audit_lock(run_id), engine=audit_lease_engine()) as held:
        yield held
