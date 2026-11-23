from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.types import ASGIApp

from strategist.tests.integration.http._share_support import (
    anonymous,
    checkpoint_tables,
    seed_thread,
    share_path,
)

pytestmark = pytest.mark.usefixtures(checkpoint_tables.__name__)


async def test_a_new_link_carries_the_context_by_default(
    app: ASGIApp,
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
    async with anonymous(app) as viewer:
        head = (await viewer.get(f"/api/v1/shared/{made['share']['token']}")).json()

    assert made["share"]["includeContext"] is True
    assert head["includeContext"] is True


async def test_the_owner_can_leave_the_context_out(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)

    made = (
        await authed_client.put(
            share_path(thread),
            json={"public": True, "allowCopy": False, "includeContext": False},
        )
    ).json()
    async with anonymous(app) as viewer:
        head = (await viewer.get(f"/api/v1/shared/{made['share']['token']}")).json()

    assert made["share"]["includeContext"] is False
    assert (await authed_client.get(share_path(thread))).json()["share"][
        "includeContext"
    ] is False
    assert head["includeContext"] is False
