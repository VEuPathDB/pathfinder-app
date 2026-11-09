from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.types import ASGIApp

from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests.integration.http._share_support import (
    CHUNKS,
    anonymous,
    checkpoint_tables,
    seed_thread,
    share_path,
)

pytestmark = pytest.mark.usefixtures(checkpoint_tables.__name__)


async def test_a_thread_starts_unshared(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)

    response = await authed_client.get(share_path(thread))

    assert response.json() == {"share": None}


async def test_a_public_link_carries_no_password(
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

    assert made["password"] is None
    assert made["share"]["public"] is True
    assert made["share"]["allowCopy"] is False
    assert len(made["share"]["token"]) >= 32
    assert (await authed_client.get(share_path(thread))).json() == {
        "share": made["share"]
    }


async def test_anyone_with_a_public_link_reads_theseed_thread(
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
    token = made["share"]["token"]

    async with anonymous(app) as viewer:
        head = (await viewer.get(f"/api/v1/shared/{token}")).json()
        snapshot = (await viewer.get(f"/api/v1/shared/{token}/snapshot")).json()

    assert head["name"] == "kinases"
    assert head["siteId"] == "plasmodb"
    assert head["assistantId"] == PATHFINDER_ASSISTANT_ID
    assert head["allowCopy"] is True
    assert head["turnInFlight"] is False
    assert head["cursor"] == snapshot["cursor"]
    assert [chunk["type"] for chunk in snapshot["chunks"]] == [
        chunk["type"] for chunk in CHUNKS
    ]


async def test_a_private_link_needs_its_password(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    made = (
        await authed_client.put(
            share_path(thread), json={"public": False, "allowCopy": False}
        )
    ).json()
    token, password = made["share"]["token"], made["password"]

    async with anonymous(app) as viewer:
        bare = await viewer.get(f"/api/v1/shared/{token}")
        wrong = await viewer.get(
            f"/api/v1/shared/{token}/snapshot",
            headers={"X-Share-Password": "not-the-password"},
        )
        right = await viewer.get(
            f"/api/v1/shared/{token}", headers={"X-Share-Password": password}
        )

    assert len(password) >= 16
    assert bare.status_code == 403
    assert bare.json()["code"] == "SHARE_LOCKED"
    assert "kinases" not in bare.text
    assert wrong.status_code == 403
    assert right.json()["name"] == "kinases"
    assert (await authed_client.get(share_path(thread))).json()["share"][
        "public"
    ] is False
    assert (
        "password" not in (await authed_client.get(share_path(thread))).json()["share"]
    )


async def test_a_new_password_locks_out_the_old(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    made = (
        await authed_client.put(
            share_path(thread), json={"public": False, "allowCopy": False}
        )
    ).json()
    token, old = made["share"]["token"], made["password"]

    new = (await authed_client.post(f"{share_path(thread)}/password")).json()[
        "password"
    ]

    async with anonymous(app) as viewer:
        with_old = await viewer.get(
            f"/api/v1/shared/{token}", headers={"X-Share-Password": old}
        )
        with_new = await viewer.get(
            f"/api/v1/shared/{token}", headers={"X-Share-Password": new}
        )
    assert new != old
    assert with_old.status_code == 403
    assert with_new.status_code == 200


async def test_a_public_link_has_no_password_to_renew(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    await authed_client.put(
        share_path(thread), json={"public": True, "allowCopy": False}
    )

    response = await authed_client.post(f"{share_path(thread)}/password")

    assert response.status_code == 409
    assert response.json()["code"] == "SHARE_IS_PUBLIC"


async def test_a_link_keeps_its_token_when_its_settings_change(
    app: ASGIApp,
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    private = (
        await authed_client.put(
            share_path(thread), json={"public": False, "allowCopy": False}
        )
    ).json()

    public = (
        await authed_client.put(
            share_path(thread), json={"public": True, "allowCopy": True}
        )
    ).json()
    private_again = (
        await authed_client.put(
            share_path(thread), json={"public": False, "allowCopy": True}
        )
    ).json()

    token = private["share"]["token"]
    assert public["share"]["token"] == token
    assert public["password"] is None
    assert private_again["share"]["token"] == token
    assert private_again["password"] not in (None, private["password"])
    async with anonymous(app) as viewer:
        stale = await viewer.get(
            f"/api/v1/shared/{token}",
            headers={"X-Share-Password": private["password"]},
        )
    assert stale.status_code == 403


async def test_a_private_link_keeps_its_password_when_copying_changes(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    await authed_client.put(
        share_path(thread), json={"public": False, "allowCopy": False}
    )

    changed = (
        await authed_client.put(
            share_path(thread), json={"public": False, "allowCopy": True}
        )
    ).json()

    assert changed["password"] is None
    assert changed["share"]["allowCopy"] is True


async def test_a_stopped_link_is_gone(
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

    stopped = await authed_client.delete(share_path(thread))

    async with anonymous(app) as viewer:
        gone = await viewer.get(f"/api/v1/shared/{made['share']['token']}")
    assert stopped.status_code == 204
    assert gone.status_code == 404
    assert gone.json()["code"] == "SHARE_NOT_FOUND"
    assert (await authed_client.get(share_path(thread))).json() == {"share": None}


async def test_a_deleted_thread_takes_its_link_with_it(
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
    async with session_maker() as session:
        row = await session.get(Conversation, thread)
        assert row is not None
        await session.delete(row)
        await session.commit()

    async with anonymous(app) as viewer:
        gone = await viewer.get(f"/api/v1/shared/{made['share']['token']}")

    assert gone.status_code == 404


async def test_an_unknown_token_is_not_found(app: ASGIApp) -> None:
    async with anonymous(app) as viewer:
        response = await viewer.get("/api/v1/shared/no-such-token/snapshot")

    assert response.status_code == 404
    assert response.json()["code"] == "SHARE_NOT_FOUND"


async def test_another_researcher_cannot_share_theseed_thread(
    authed_client: httpx.AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, uuid4())

    response = await authed_client.put(
        share_path(thread), json={"public": True, "allowCopy": False}
    )

    assert response.status_code == 404


async def test_two_first_links_at_once_make_one_link(
    authed_client: httpx.AsyncClient,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    thread = await seed_thread(session_maker, authed_user_id)
    settings = {"public": True, "allowCopy": False}

    first, second = await asyncio.gather(
        authed_client.put(share_path(thread), json=settings),
        authed_client.put(share_path(thread), json=settings),
    )

    assert [first.status_code, second.status_code] == [200, 200]
    assert first.json()["share"]["token"] == second.json()["share"]["token"]
