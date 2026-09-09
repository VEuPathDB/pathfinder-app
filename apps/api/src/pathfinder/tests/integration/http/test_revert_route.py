from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.persistence.models import Conversation, Message
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import User
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.security import create_user_token


@pytest.fixture(scope="module", autouse=True)
async def _langgraph_checkpoint_tables(
    patch_app_db_engine: None,
) -> AsyncGenerator[None]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield


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


def _client(app: FastAPI, user_id: UUID) -> httpx.AsyncClient:
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    client.cookies.set("pathfinder-auth", create_user_token(user_id))
    return client


@pytest.fixture
async def api_client(
    app: FastAPI,
    patch_app_db_engine: None,
    seed_user: User,
    signed_in_to_veupathdb: None,
) -> AsyncGenerator[httpx.AsyncClient]:
    """A revert restores a strategy on WDK, so the route requires the login."""
    del patch_app_db_engine, signed_in_to_veupathdb
    async with _client(app, seed_user.id) as client:
        yield client


@pytest.fixture
async def signed_out_client(
    app: FastAPI,
    patch_app_db_engine: None,
    seed_user: User,
) -> AsyncGenerator[httpx.AsyncClient]:
    """The owner of the thread, holding no VEuPathDB session."""
    del patch_app_db_engine
    async with _client(app, seed_user.id) as client:
        yield client


@pytest.fixture
async def api_client_other_user(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    signed_in_to_veupathdb: None,
) -> AsyncGenerator[httpx.AsyncClient]:
    del patch_app_db_engine, signed_in_to_veupathdb
    other = User(id=uuid4())
    db_session.add(other)
    await db_session.flush()
    await db_session.commit()
    async with _client(app, other.id) as client:
        yield client


@pytest.fixture
async def conv_with_messages(
    db_session: AsyncSession,
    seed_user: User,
) -> tuple[UUID, list[Message]]:
    conv = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=seed_user.id,
        site_id="plasmodb",
        name="",
    )
    db_session.add(conv)
    await db_session.flush()
    msgs: list[Message] = []
    base = datetime.now(UTC)
    for i, (role, _text_body) in enumerate(
        (
            ("user", "one"),
            ("assistant", "reply one"),
            ("user", "two"),
            ("assistant", "reply two"),
        )
    ):
        msg = Message(
            id=uuid4(),
            conversation_id=conv.id,
            role=role,
            metadata_={},
            created_at=base + timedelta(seconds=i),
        )
        db_session.add(msg)
        msgs.append(msg)
    await db_session.flush()
    await db_session.commit()
    return conv.id, msgs


async def test_revert_truncates_messages(
    api_client: httpx.AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    conv_with_messages: tuple[UUID, list[Message]],
) -> None:
    conv_id, msgs = conv_with_messages
    target = msgs[2]
    res = await api_client.post(
        f"/api/v1/conversations/{conv_id}/revert-to-message",
        json={"messageId": str(target.id)},
    )
    assert res.status_code == 204
    async with session_maker() as s:
        remaining = (
            await s.scalars(
                select(Message).where(Message.conversation_id == conv_id),
            )
        ).all()
    assert {m.id for m in remaining} == {msgs[0].id, msgs[1].id}


async def test_revert_rejects_non_user_target(
    api_client: httpx.AsyncClient,
    conv_with_messages: tuple[UUID, list[Message]],
) -> None:
    conv_id, msgs = conv_with_messages
    assistant = msgs[1]
    res = await api_client.post(
        f"/api/v1/conversations/{conv_id}/revert-to-message",
        json={"messageId": str(assistant.id)},
    )
    assert res.status_code == 404


async def test_revert_rejects_wrong_user(
    api_client_other_user: httpx.AsyncClient,
    conv_with_messages: tuple[UUID, list[Message]],
) -> None:
    conv_id, msgs = conv_with_messages
    target = msgs[2]
    res = await api_client_other_user.post(
        f"/api/v1/conversations/{conv_id}/revert-to-message",
        json={"messageId": str(target.id)},
    )
    assert res.status_code == 404


async def test_revert_ghost_message_is_noop(
    api_client: httpx.AsyncClient,
    conv_with_messages: tuple[UUID, list[Message]],
) -> None:
    # A never-persisted target (e.g. a rejected/failed send) is a no-op (204),
    # not a 404 — otherwise edit/retry on a failed message breaks.
    conv_id, _msgs = conv_with_messages
    res = await api_client.post(
        f"/api/v1/conversations/{conv_id}/revert-to-message",
        json={"messageId": str(uuid4())},
    )
    assert res.status_code == 204


async def test_revert_without_a_veupathdb_login_is_refused(
    signed_out_client: httpx.AsyncClient,
    conv_with_messages: tuple[UUID, list[Message]],
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A revert pushes the restored snapshot, so it needs the same identity
    the branch route requires. Nothing is deleted by the refusal."""
    conv_id, msgs = conv_with_messages
    res = await signed_out_client.post(
        f"/api/v1/conversations/{conv_id}/revert-to-message",
        json={"messageId": str(msgs[2].id)},
    )
    assert res.status_code == 401, res.text
    assert res.json()["code"] == "WDK_LOGIN_REQUIRED"
    async with session_maker() as s:
        remaining = (
            await s.scalars(select(Message).where(Message.conversation_id == conv_id))
        ).all()
    assert {m.id for m in remaining} == {m.id for m in msgs}
