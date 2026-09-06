from __future__ import annotations

from uuid import UUID

import pytest
from assistant_core.memory.store import MemoryStore
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import DBSessionFactory
from langgraph.store.postgres.aio import AsyncPostgresStore
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RunUsage
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy.session import StrategySession

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.scratchpad import tools
from pathfinder.persistence.models import User


@pytest.fixture
async def conv_id(db_session: AsyncSession, seed_user: User) -> UUID:
    conv = Conversation(
        user_id=seed_user.id,
        site_id="plasmodb",
        name="",
    )
    db_session.add(conv)
    await db_session.flush()
    await db_session.commit()
    return conv.id


def _run_ctx(
    *,
    conv_id: UUID,
    db_session_factory: DBSessionFactory,
    user_id: UUID,
    memory_store: AsyncPostgresStore,
) -> RunContext[AgentDeps]:
    deps = AgentDeps(
        site_id="plasmodb",
        strategy_session=StrategySession(site_id="plasmodb"),
        conversation_id=conv_id,
        user_id=user_id,
        db_session_factory=db_session_factory,
        memory_store=memory_store,
    )
    return RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        tool_name="promote_to_memory",
        tool_call_id="tc-1",
    )


async def test_promote_creates_memory_and_keeps_note(
    db_session: AsyncSession,
    db_session_factory: DBSessionFactory,
    conv_id: UUID,
    seed_user: User,
    memory_store: AsyncPostgresStore,
) -> None:
    del db_session
    ctx = _run_ctx(
        conv_id=conv_id,
        db_session_factory=db_session_factory,
        user_id=seed_user.id,
        memory_store=memory_store,
    )
    created = await tools.note(
        ctx,
        title="Gametocyte stage-specific markers",
        summary="PF3D7 ring/trophozoite vs mature stage V",
        body="Pfs25, Pfs230 mark mature gametocytes; verified in PlasmoDB.",
        tags=["stage:gametocyte"],
    )
    assert isinstance(created.return_value, dict)
    nid = created.return_value["id"]
    assert isinstance(nid, str)

    key = (await tools.promote_to_memory(ctx, note_id=nid)).return_value
    assert isinstance(key, str)
    assert key

    # Scratchpad note still exists
    read = (await tools.read_note(ctx, note_id=nid)).return_value
    assert read["title"] == "Gametocyte stage-specific markers"

    # Memory is actually in the store under the knowledge namespace
    wrapped = MemoryStore(store=memory_store)
    stored = await wrapped.get(
        user_id=seed_user.id,
        kind="knowledge",
        key=key,
    )
    assert stored is not None
    assert stored.value.name == "Gametocyte stage-specific markers"
    assert stored.value.site_id == "plasmodb"
    assert stored.value.content["source_note_id"] == nid
    assert (
        stored.value.content["body"]
        == "Pfs25, Pfs230 mark mature gametocytes; verified in PlasmoDB."
    )


async def test_promote_missing_note_raises(
    db_session: AsyncSession,
    db_session_factory: DBSessionFactory,
    conv_id: UUID,
    seed_user: User,
    memory_store: AsyncPostgresStore,
) -> None:
    del db_session
    ctx = _run_ctx(
        conv_id=conv_id,
        db_session_factory=db_session_factory,
        user_id=seed_user.id,
        memory_store=memory_store,
    )
    with pytest.raises(ModelRetry):
        await tools.promote_to_memory(ctx, note_id="n-nope")


async def test_promote_missing_memory_store_raises(
    db_session: AsyncSession,
    db_session_factory: DBSessionFactory,
    conv_id: UUID,
    seed_user: User,
) -> None:
    del db_session
    deps = AgentDeps(
        site_id="plasmodb",
        strategy_session=StrategySession(site_id="plasmodb"),
        conversation_id=conv_id,
        user_id=seed_user.id,
        db_session_factory=db_session_factory,
    )
    ctx = RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        tool_name="promote_to_memory",
        tool_call_id="tc-1",
    )
    with pytest.raises(ModelRetry):
        await tools.promote_to_memory(ctx, note_id="n-whatever")
