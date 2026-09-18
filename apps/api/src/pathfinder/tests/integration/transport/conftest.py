"""Fixtures the transport tier shares, and the app the conformance run drives."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import httpx
import procrastinate
import pytest
from assistant_core.conversation.checkpointer import to_psycopg_url
from assistant_core.persistence.models import Conversation
from assistant_core.platform import db
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pathfinder.domain.memory import MEMORY_KINDS
from pathfinder.jobs.app import procrastinate_app
from pathfinder.main import create_app
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.readiness import _FIXED_SUBSYSTEMS, get_readiness
from pathfinder.platform.security import create_user_token
from pathfinder.tests._support.memory_store_double import (
    LoopFreeMemoryStore,
    seed_key,
    seeded_memory,
)
from pathfinder.transport.http.deps import get_memory_store
from pathfinder.transport.http.routers import veupathdb_auth


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
async def seed_user(db_session: AsyncSession) -> User:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user


@pytest.fixture
async def conversation(db_session: AsyncSession, seed_user: User) -> Conversation:
    conv = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        id=uuid4(),
        user_id=seed_user.id,
        site_id="plasmodb",
        name="snapshot-fixture",
    )
    db_session.add(conv)
    await db_session.flush()
    db_session.add(
        ConversationStrategy(conversation_id=conv.id, record_type="transcript"),
    )
    await db_session.commit()
    return conv


@pytest.fixture
async def api_client(
    app: FastAPI,
    seed_user: User,
) -> AsyncGenerator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    token = create_user_token(seed_user.id)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"authorization": f"Bearer {token}"},
    ) as client:
        yield client


async def _reject_login(
    site_id: str, email: str, password: str, *, redirect_url: str = "/"
) -> str | None:
    """Refuse the fuzzer's random credentials without a call to VEuPathDB.

    The live sign-in would answer 5xx whenever a VEuPathDB site is down, and
    the check cannot tell that from a fault of this server.
    """
    del site_id, email, password, redirect_url
    return None


@asynccontextmanager
async def _noop_lifespan(_: FastAPI) -> AsyncGenerator[None]:
    """Stand in for the app lifespan. The fixtures own the database and the
    engine, so the startup chain stays out of every fuzz call.
    """
    yield


@pytest.fixture(scope="session")
def conformance_memory_store() -> LoopFreeMemoryStore:
    """The store the conformance app serves for the whole fuzz session."""
    return LoopFreeMemoryStore()


@pytest.fixture
def seeded_memories(
    patched_app: tuple[FastAPI, UUID],
    conformance_memory_store: LoopFreeMemoryStore,
) -> LoopFreeMemoryStore:
    """One memory of every kind for the fuzzed user.

    The purge deletes the user's memories, so the seed is written again
    before every test rather than once for the session.
    """
    _, user_id = patched_app
    conformance_memory_store.rows.clear()
    for kind in MEMORY_KINDS:
        conformance_memory_store.rows[(user_id, kind, seed_key(kind))] = seeded_memory(
            kind
        )
    return conformance_memory_store


@pytest.fixture(scope="session")
async def patched_app(
    db_engine: AsyncEngine,
    session_maker: async_sessionmaker[Any],
    conformance_memory_store: LoopFreeMemoryStore,
) -> AsyncGenerator[tuple[FastAPI, UUID]]:
    """Build the app once per session against the test database, seed one
    user, and serve the memory store from a loop-free double.
    """
    db._engine = db_engine
    db._session_factory_instance = session_maker

    get_settings.cache_clear()
    test_connector = procrastinate.PsycopgConnector(
        conninfo=to_psycopg_url(get_settings().database_url),
    )
    procrastinate_app.connector = test_connector
    procrastinate_app.job_manager.connector = test_connector

    async with db_engine.begin() as conn:
        await conn.exec_driver_sql(
            "TRUNCATE TABLE "
            "messages, conversations, exports, "
            "experiments, gene_sets, control_sets, users "
            "RESTART IDENTITY CASCADE",
        )

    app = create_app()
    app.router.lifespan_context = _noop_lifespan
    # The conformance client runs the app on a portal loop of its own, which a
    # store opened by any fixture cannot serve.
    app.dependency_overrides[get_memory_store] = lambda: conformance_memory_store

    user_id = uuid4()
    async with session_maker() as session:
        session.add(User(id=user_id))
        await session.commit()

    readiness = get_readiness()
    for subsystem in _FIXED_SUBSYSTEMS:
        readiness.mark_ready(subsystem)
    # Readiness also needs one loaded site catalog; this app loads none.
    readiness.mark_catalog_ready("plasmodb")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(veupathdb_auth, "password_login", _reject_login)
        # A cancel reads the job table, so the served app needs an open app.
        async with procrastinate_app.open_async():
            yield app, user_id
