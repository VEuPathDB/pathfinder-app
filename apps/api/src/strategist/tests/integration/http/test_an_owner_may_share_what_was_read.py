from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import ConversationEvent
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.types import ASGIApp

from strategist.ai.graph.state import StrategyDomainState
from strategist.persistence.models import User
from strategist.tests.integration.http._share_support import (
    SERDE,
    anonymous,
    checkpoint_tables,
    seed_owners_state,
    seed_thread,
    share_path,
)
from strategist.tests.integration.http.conftest import client_for

pytestmark = pytest.mark.usefixtures(checkpoint_tables.__name__)

_SHARING_READS = {"public": True, "allowCopy": True, "includeAccountReads": True}


async def test_a_link_hides_the_reads_until_the_owner_includes_them(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)

    made = (
        await authed_client.put(
            share_path(thread), json={"public": True, "allowCopy": False}
        )
    ).json()
    included = (await authed_client.put(share_path(thread), json=_SHARING_READS)).json()

    assert made["share"]["includeAccountReads"] is False
    assert included["share"]["includeAccountReads"] is True
    assert (await authed_client.get(share_path(thread))).json()["share"][
        "includeAccountReads"
    ] is True


async def test_an_included_read_reaches_the_viewer(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    await seed_owners_state(session_maker, thread)
    made = (await authed_client.put(share_path(thread), json=_SHARING_READS)).json()

    async with anonymous(app) as viewer:
        snapshot = await viewer.get(f"/api/v1/shared/{made['share']['token']}/snapshot")

    outputs = [
        c for c in snapshot.json()["chunks"] if c["type"] == "tool-output-available"
    ]
    assert [c["output"] for c in outputs] == [{"threads": ["Malaria antigens"]}]


async def test_a_copy_keeps_included_reads_and_still_drops_the_owners_controls(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    signed_in_to_veupathdb: None,
) -> None:
    del signed_in_to_veupathdb
    thread = await seed_thread(session_maker, authed_user_id)
    await seed_owners_state(session_maker, thread)
    made = (await authed_client.put(share_path(thread), json=_SHARING_READS)).json()
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
    assert "Malaria antigens" in json.dumps(list(chunks))
    assert domain.control_sets == []
