from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation, ConversationEvent, Message
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.types import ASGIApp

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.domain.owner_reads import NOT_SHARED
from pathfinder.persistence.models import User
from pathfinder.tests.integration.http._share_support import (
    SERDE,
    anonymous,
    checkpoint_tables,
    seed_owners_state,
    seed_thread,
    share_path,
)
from pathfinder.tests.integration.http.conftest import client_for

pytestmark = pytest.mark.usefixtures(checkpoint_tables.__name__)


async def test_a_viewer_copies_the_thread_into_their_account(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    signed_in_to_veupathdb: None,
) -> None:
    del signed_in_to_veupathdb
    thread = await seed_thread(session_maker, authed_user_id)
    made = (
        await authed_client.put(
            share_path(thread), json={"public": False, "allowCopy": True}
        )
    ).json()
    viewer_id = uuid4()
    async with session_maker() as session:
        session.add(User(id=viewer_id))
        await session.commit()

    async with client_for(app, viewer_id) as viewer:
        response = await viewer.post(
            f"/api/v1/shared/{made['share']['token']}/copy",
            headers={"X-Share-Password": made["password"]},
        )

    copy_id = UUID(response.json()["id"])
    async with session_maker() as session:
        copy = await session.get(Conversation, copy_id)
        messages = (
            await session.scalars(
                select(Message).where(Message.conversation_id == copy_id)
            )
        ).all()
    assert copy is not None
    assert copy.user_id == viewer_id
    assert copy.name == "kinases (copy)"
    assert copy.parent_conversation_id is None
    assert len(messages) == 1


async def test_a_link_that_refuses_copies_is_not_copied(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    signed_in_to_veupathdb: None,
) -> None:
    del signed_in_to_veupathdb
    thread = await seed_thread(session_maker, authed_user_id)
    made = (
        await authed_client.put(
            share_path(thread), json={"public": True, "allowCopy": False}
        )
    ).json()
    viewer_id = uuid4()
    async with session_maker() as session:
        session.add(User(id=viewer_id))
        await session.commit()

    async with client_for(app, viewer_id) as viewer:
        response = await viewer.post(f"/api/v1/shared/{made['share']['token']}/copy")

    assert response.status_code == 403
    assert response.json()["code"] == "SHARE_COPY_NOT_ALLOWED"


async def test_a_signed_out_viewer_cannot_copy(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    made = (
        await authed_client.put(
            share_path(thread), json={"public": True, "allowCopy": True}
        )
    ).json()

    async with anonymous(app) as viewer:
        response = await viewer.post(f"/api/v1/shared/{made['share']['token']}/copy")

    assert response.status_code == 401


async def test_a_viewer_never_reads_what_the_owner_read_of_their_account(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    await seed_owners_state(session_maker, thread)
    made = (
        await authed_client.put(
            share_path(thread), json={"public": True, "allowCopy": False}
        )
    ).json()

    async with anonymous(app) as viewer:
        snapshot = await viewer.get(f"/api/v1/shared/{made['share']['token']}/snapshot")

    assert "Malaria antigens" not in snapshot.text
    outputs = [
        c for c in snapshot.json()["chunks"] if c["type"] == "tool-output-available"
    ]
    assert [c["output"] for c in outputs] == [NOT_SHARED]


async def test_a_copy_holds_neither_the_owners_reads_nor_their_controls(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    signed_in_to_veupathdb: None,
) -> None:
    del signed_in_to_veupathdb
    thread = await seed_thread(session_maker, authed_user_id)
    await seed_owners_state(session_maker, thread)
    made = (
        await authed_client.put(
            share_path(thread), json={"public": True, "allowCopy": True}
        )
    ).json()
    viewer_id = uuid4()
    async with session_maker() as session:
        session.add(User(id=viewer_id))
        await session.commit()

    async with client_for(app, viewer_id) as viewer:
        copy_id = (
            await viewer.post(f"/api/v1/shared/{made['share']['token']}/copy")
        ).json()["id"]

    async with session_maker() as session:
        chunks = (
            await session.scalars(
                select(ConversationEvent.chunk).where(
                    ConversationEvent.conversation_id == UUID(copy_id)
                )
            )
        ).all()
        row = (
            await session.execute(
                text(
                    "SELECT type, blob FROM checkpoint_blobs "
                    "WHERE thread_id = :thread AND channel = 'domain'"
                ),
                {"thread": copy_id},
            )
        ).one()
    domain = StrategyDomainState.model_validate(
        SERDE.loads_typed((row.type, bytes(row.blob)))
    )
    assert "Malaria antigens" not in json.dumps(list(chunks))
    assert domain.control_sets == []
    assert domain.original_request == "Kinases on chromosome 3"
