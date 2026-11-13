from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Iterator
from uuid import uuid4

import pytest
from assistant_core.memory.lifespan import lifespan_memory_store
from assistant_core.persistence.models import Conversation
from assistant_core.spec import TurnContextRequest
from langgraph.store.postgres.aio import AsyncPostgresStore
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from strategist.ai.audit.turn import build_turn_context as build_audit_context
from strategist.assistants.strategist_spec import build_turn_context
from strategist.jobs.runtime import build_worker_runtime_context
from strategist.persistence.models import User
from strategist.platform.config import get_settings
from strategist.platform.identity import STRATEGIST_ASSISTANT_ID


@pytest.fixture
async def store(
    patch_app_db_engine: None, db_cleaner: None
) -> AsyncGenerator[AsyncPostgresStore]:
    del patch_app_db_engine, db_cleaner
    async with lifespan_memory_store(os.environ["DATABASE_URL"]) as raw:
        yield raw


async def _thread(
    session_maker: async_sessionmaker[AsyncSession], *, memory_enabled: bool | None
) -> Conversation:
    user_id = uuid4()
    conversation = Conversation(
        assistant_id=STRATEGIST_ASSISTANT_ID,
        id=uuid4(),
        user_id=user_id,
        site_id="plasmodb",
        name="kinases",
    )
    async with session_maker() as session:
        session.add(User(id=user_id, memory_enabled=memory_enabled))
        await session.flush()
        session.add(conversation)
        await session.commit()
    return conversation


def _request(
    conversation: Conversation, store: AsyncPostgresStore
) -> TurnContextRequest:
    return TurnContextRequest(
        conversation=conversation,
        site_id="plasmodb",
        user_id=conversation.user_id,
        memory_store=store,
        cancel_event=asyncio.Event(),
        phase_models={},
        phase_reasoning={},
    )


async def test_a_turn_of_a_researcher_with_memory_on_reads_the_store(
    store: AsyncPostgresStore, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    thread = await _thread(session_maker, memory_enabled=True)

    context = await build_turn_context(_request(thread, store))

    assert context.memory_store is store


async def test_a_turn_of_a_researcher_with_memory_off_has_no_store(
    store: AsyncPostgresStore, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    thread = await _thread(session_maker, memory_enabled=False)

    context = await build_turn_context(_request(thread, store))

    assert (context.user_id, context.memory_store) == (thread.user_id, None)


async def test_an_audit_turn_with_memory_off_has_no_store(
    store: AsyncPostgresStore, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    thread = await _thread(session_maker, memory_enabled=False)

    context = await build_audit_context(_request(thread, store))

    assert (context.user_id, context.memory_store) == (thread.user_id, None)


async def test_a_task_of_a_researcher_with_memory_off_has_no_store(
    store: AsyncPostgresStore, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    thread = await _thread(session_maker, memory_enabled=False)

    context = await build_worker_runtime_context(
        conversation_id=thread.id, memory_store=store
    )

    assert (context.user_id, context.memory_store) == (thread.user_id, None)


@pytest.fixture
def memory_on_by_default(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("MEMORY_ON_BY_DEFAULT", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_an_unset_account_has_no_store_on_a_deployment_that_keeps_memory_off(
    store: AsyncPostgresStore, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    thread = await _thread(session_maker, memory_enabled=None)

    context = await build_turn_context(_request(thread, store))

    assert (context.user_id, context.memory_store) == (thread.user_id, None)


async def test_an_unset_account_reads_the_store_on_a_deployment_that_turns_memory_on(
    store: AsyncPostgresStore,
    session_maker: async_sessionmaker[AsyncSession],
    memory_on_by_default: None,
) -> None:
    del memory_on_by_default
    thread = await _thread(session_maker, memory_enabled=None)

    context = await build_turn_context(_request(thread, store))

    assert context.memory_store is store
