from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.security import create_user_token


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
