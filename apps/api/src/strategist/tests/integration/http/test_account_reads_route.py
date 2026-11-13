from __future__ import annotations

from uuid import UUID, uuid4

import httpx
from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from strategist.persistence.models import User
from strategist.platform.identity import STRATEGIST_ASSISTANT_ID
from strategist.services.conversations.account_reads import account_reads_allowed


def _reads(conversation_id: UUID) -> str:
    return f"/api/v1/conversations/{conversation_id}/account-reads"


async def _thread(
    session_maker: async_sessionmaker[AsyncSession], user_id: UUID
) -> UUID:
    conversation_id = uuid4()
    async with session_maker() as session:
        if await session.get(User, user_id) is None:
            session.add(User(id=user_id))
            await session.flush()
        session.add(
            Conversation(
                assistant_id=STRATEGIST_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="kinases",
            )
        )
        await session.commit()
    return conversation_id


async def test_an_answer_holds_for_the_thread(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await _thread(session_maker, authed_user_id)

    response = await authed_client.put(_reads(thread), json={"allowed": True})

    assert response.json() == {"allowed": True}
    async with session_maker() as session:
        assert await account_reads_allowed(
            session, conversation_id=thread, user_id=authed_user_id
        )


async def test_another_researchers_thread_is_not_found(
    authed_client: httpx.AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await _thread(session_maker, uuid4())

    response = await authed_client.put(_reads(thread), json={"allowed": True})

    assert response.status_code == 404


async def test_an_account_does_not_always_allow_by_default(
    authed_client: httpx.AsyncClient,
) -> None:
    response = await authed_client.get("/api/v1/me/account-reads")

    assert response.json() == {"always": False}


async def test_always_allowing_holds_for_the_account(
    authed_client: httpx.AsyncClient,
) -> None:
    await authed_client.put("/api/v1/me/account-reads", json={"always": True})

    assert (await authed_client.get("/api/v1/me/account-reads")).json() == {
        "always": True
    }
