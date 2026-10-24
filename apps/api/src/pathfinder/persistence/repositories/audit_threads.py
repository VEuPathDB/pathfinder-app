from __future__ import annotations

from uuid import UUID

from assistant_core.platform.context import calling_application
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import AuditRun

__all__ = ["AuditThreadRepository"]


class AuditThreadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def holds_runs(self, *, conversation_id: UUID) -> bool:
        held = select(AuditRun.id).where(
            AuditRun.conversation_id == conversation_id,
            AuditRun.application_id == calling_application(),
        )
        return bool(await self.session.scalar(select(held.exists())))
