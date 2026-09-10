from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.persistence.repositories.scratchpad import ScratchpadRepository
from assistant_core.scratchpad.models import NoteCreate
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import User
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
def db_session_factory(
    session_maker: async_sessionmaker[AsyncSession],
) -> async_sessionmaker[AsyncSession]:
    return session_maker


@pytest.fixture
async def seed_user(db_session: AsyncSession) -> User:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user


@pytest.fixture
async def api_client(
    app: FastAPI,
    patch_app_db_engine: None,
    seed_user: User,
) -> AsyncGenerator[httpx.AsyncClient]:
    """Client authenticated as ``seed_user``.

    Bound to the same FastAPI app + test DB engine as the other fixtures, so
    writes made through ``db_session_factory`` are visible to the routes.
    """
    del patch_app_db_engine
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        client.cookies.set("pathfinder-auth", create_user_token(seed_user.id))
        yield client


@pytest.fixture
async def api_client_other_user(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
) -> AsyncGenerator[httpx.AsyncClient]:
    """Client authenticated as a different user than ``seed_user``."""
    del patch_app_db_engine
    other = User(id=uuid4())
    db_session.add(other)
    await db_session.flush()
    await db_session.commit()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        client.cookies.set("pathfinder-auth", create_user_token(other.id))
        yield client


@pytest.fixture
async def conv_id(db_session: AsyncSession, seed_user: User) -> UUID:
    conv = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=seed_user.id,
        site_id="plasmodb",
        name="",
    )
    db_session.add(conv)
    await db_session.flush()
    await db_session.commit()
    return conv.id


class TestListAndGet:
    async def test_list_empty(
        self,
        api_client: httpx.AsyncClient,
        conv_id: UUID,
    ) -> None:
        res = await api_client.get(
            f"/api/v1/conversations/{conv_id}/scratchpad/notes",
        )
        assert res.status_code == 200
        assert res.json() == []

    async def test_list_populated(
        self,
        api_client: httpx.AsyncClient,
        db_session_factory: async_sessionmaker[AsyncSession],
        conv_id: UUID,
    ) -> None:
        async with db_session_factory() as s:
            repo = ScratchpadRepository(s)
            await repo.create(
                conversation_id=conv_id,
                data=NoteCreate(title="t", summary="s", body="b"),
            )
            await s.commit()
        res = await api_client.get(
            f"/api/v1/conversations/{conv_id}/scratchpad/notes",
        )
        assert res.status_code == 200
        body = res.json()
        assert len(body) == 1
        assert body[0]["title"] == "t"
        assert "body" in body[0]


class TestPatchPinOnly:
    async def test_patch_pinned_true(
        self,
        api_client: httpx.AsyncClient,
        db_session_factory: async_sessionmaker[AsyncSession],
        conv_id: UUID,
    ) -> None:
        async with db_session_factory() as s:
            repo = ScratchpadRepository(s)
            created = await repo.create(
                conversation_id=conv_id,
                data=NoteCreate(title="t", summary="s", body="b"),
            )
            await s.commit()
        res = await api_client.patch(
            f"/api/v1/conversations/{conv_id}/scratchpad/notes/{created.id}",
            json={"pinned": True},
        )
        assert res.status_code == 200
        assert res.json()["pinned"] is True

    async def test_patch_forbids_body_edit(
        self,
        api_client: httpx.AsyncClient,
        db_session_factory: async_sessionmaker[AsyncSession],
        conv_id: UUID,
    ) -> None:
        async with db_session_factory() as s:
            repo = ScratchpadRepository(s)
            created = await repo.create(
                conversation_id=conv_id,
                data=NoteCreate(title="t", summary="s", body="b"),
            )
            await s.commit()
        res = await api_client.patch(
            f"/api/v1/conversations/{conv_id}/scratchpad/notes/{created.id}",
            json={"title": "user-edited title"},
        )
        assert res.status_code == 422


class TestDelete:
    async def test_delete_204(
        self,
        api_client: httpx.AsyncClient,
        db_session_factory: async_sessionmaker[AsyncSession],
        conv_id: UUID,
    ) -> None:
        async with db_session_factory() as s:
            repo = ScratchpadRepository(s)
            created = await repo.create(
                conversation_id=conv_id,
                data=NoteCreate(title="t", summary="s", body="b"),
            )
            await s.commit()
        res = await api_client.delete(
            f"/api/v1/conversations/{conv_id}/scratchpad/notes/{created.id}",
        )
        assert res.status_code == 204
        follow_up = await api_client.get(
            f"/api/v1/conversations/{conv_id}/scratchpad/notes",
        )
        assert follow_up.json() == []


class TestAuthz:
    async def test_wrong_user_404(
        self,
        api_client_other_user: httpx.AsyncClient,
        conv_id: UUID,
    ) -> None:
        res = await api_client_other_user.get(
            f"/api/v1/conversations/{conv_id}/scratchpad/notes",
        )
        assert res.status_code == 404
