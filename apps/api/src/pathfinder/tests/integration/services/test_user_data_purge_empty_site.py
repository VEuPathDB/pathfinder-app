"""A purge that names an empty site clears every site."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from assistant_core.memory.store import MemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.persistence.models import EvalStagedCase, User
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.services.user_data import purge_user_data
from pathfinder.tests.integration.http._user_data_purge import (
    OTHER_SITE,
    SITE,
    add_conv,
    add_staged_case,
)


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    patch_app_db_engine: None,
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del patch_app_db_engine, db_cleaner
    async with session_maker() as session:
        yield session


async def test_an_empty_site_purges_every_sites_staged_cases_and_audits(
    db_session: AsyncSession,
    app_memory_store: MemoryStore,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    owner = User(id=uuid4())
    db_session.add(owner)
    await db_session.commit()
    for site_id, gene in ((SITE, "PF3D7_1133400"), (OTHER_SITE, "TGME49_200250")):
        conversation_id = await add_conv(
            db_session,
            owner.id,
            site_id=site_id,
            wdk_strategy_id=None,
            created_here=False,
        )
        await add_staged_case(
            db_session, owner.id, site_id=site_id, conversation_id=conversation_id
        )
        await create_run(
            owner=RunOwner(user_id=owner.id, conversation_id=conversation_id),
            scope=AuditScope(
                site_id=site_id,
                targets=(SingleGeneTarget(check="gene_length", genes=(gene,)),),
            ),
        )

    async with session_maker() as session:
        result = await purge_user_data(
            session=session,
            user_id=owner.id,
            site_id="",
            delete_wdk=False,
            memory_store=app_memory_store,
        )

    assert (result.staged_eval_cases, result.audit_runs) == (2, 2)
    async with session_maker() as verify:
        staged = await verify.scalars(
            select(EvalStagedCase.id).where(EvalStagedCase.user_id == owner.id),
        )
        assert list(staged) == []
        assert await AuditRepository(verify).runs(user_id=owner.id) == []
