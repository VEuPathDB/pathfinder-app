"""Creating an audit run, and reading one the caller may act on."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.audit.scope import AuditScope
from pathfinder.persistence.models import AuditRunRecord
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.platform.errors import NotFoundError

_SEED_BITS = 31


@dataclass(frozen=True, kw_only=True)
class RunOwner:
    user_id: UUID
    conversation_id: UUID


def _missing(run_id: UUID) -> NotFoundError:
    return NotFoundError(
        title="Audit run not found", detail=f"no audit run {run_id} here"
    )


async def add_run(session: AsyncSession, *, owner: RunOwner, scope: AuditScope) -> UUID:
    return await AuditRepository(session).create_run(
        user_id=owner.user_id,
        conversation_id=owner.conversation_id,
        scope=scope,
        seed=secrets.randbits(_SEED_BITS),
    )


async def create_run(*, owner: RunOwner, scope: AuditScope) -> UUID:
    async with async_session_factory() as session:
        run_id = await add_run(session, owner=owner, scope=scope)
        await session.commit()
    return run_id


async def readable_run(run_id: UUID, user_id: UUID) -> AuditRunRecord:
    async with async_session_factory() as session:
        run = await AuditRepository(session).run(run_id, user_id=user_id)
    if run is None:
        raise _missing(run_id)
    return run


async def owned_run(run_id: UUID, owner: RunOwner) -> AuditRunRecord:
    run = await readable_run(run_id, owner.user_id)
    if run.conversation_id != owner.conversation_id:
        raise _missing(run_id)
    return run
