from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import ConversationStrategy, GeneSetRow, User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.security import create_user_token
from pathfinder.services import user_data
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.tests.integration.http.conftest import (
    OTHER_APPLICATION_ID,
    other_application_client_for,
)

SITE = "plasmodb"
MINE = 101
THEIRS = 202
UNREFERENCED = 303


@dataclass(frozen=True)
class _Summary:
    strategy_id: int


@dataclass
class _FakeStrategyApi:
    """Records the WDK strategies a purge asks it to delete."""

    deleted: list[int] = field(default_factory=list)

    async def list_strategies(self) -> list[_Summary]:
        return [_Summary(MINE), _Summary(THEIRS), _Summary(UNREFERENCED)]

    async def delete_strategy(self, strategy_id: int) -> None:
        self.deleted.append(strategy_id)


@pytest.fixture
def wdk_api(monkeypatch: pytest.MonkeyPatch) -> _FakeStrategyApi:
    api = _FakeStrategyApi()
    monkeypatch.setattr(user_data, "get_strategy_api", lambda _site: api)
    return api


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
async def api_client(
    app: FastAPI,
    patch_app_db_engine: None,
    seed_user: User,
) -> AsyncGenerator[httpx.AsyncClient]:
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
async def other_application_client(
    app: FastAPI,
    patch_app_db_engine: None,
    seed_user: User,
    other_application: str,
) -> AsyncGenerator[httpx.AsyncClient]:
    """The same user, calling from a second application."""
    del patch_app_db_engine, other_application
    async with other_application_client_for(app, seed_user.id) as client:
        yield client


async def _add_conv(
    session: AsyncSession,
    user_id: UUID,
    *,
    site_id: str,
    wdk_strategy_id: int | None,
    application_id: str = "pathfinder",
) -> UUID:
    conv = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        id=uuid4(),
        user_id=user_id,
        application_id=application_id,
        site_id=site_id,
        name="c",
    )
    session.add(conv)
    await session.flush()
    if wdk_strategy_id is not None:
        session.add(
            ConversationStrategy(
                conversation_id=conv.id,
                wdk_strategy_id=wdk_strategy_id,
            ),
        )
        await session.flush()
    await session.commit()
    return conv.id


async def test_purge_dismisses_all_conversations_and_reports_counts(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    no_wdk = await _add_conv(
        db_session, seed_user.id, site_id="plasmodb", wdk_strategy_id=None
    )
    wdk_linked = await _add_conv(
        db_session, seed_user.id, site_id="plasmodb", wdk_strategy_id=555
    )

    resp = await api_client.request(
        "DELETE", "/api/v1/user/data", params={"siteId": "plasmodb"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "ok": True,
        "deleted": {
            "strategies": 2,
            "wdkStrategies": 0,
            "geneSets": 0,
            "experiments": 0,
            "controlSets": 0,
            "stagedEvalCases": 0,
        },
    }

    async with session_maker() as verify:
        rows = (
            (
                await verify.execute(
                    select(Conversation).where(Conversation.user_id == seed_user.id)
                )
            )
            .scalars()
            .all()
        )
    by_id = {c.id: c for c in rows}
    assert set(by_id) == {no_wdk, wdk_linked}
    assert by_id[no_wdk].dismissed_at is not None
    assert by_id[wdk_linked].dismissed_at is not None


async def test_a_purge_from_another_application_destroys_nothing(
    api_client: httpx.AsyncClient,
    other_application_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A caller destroys only what it can see."""
    conversation = await _add_conv(
        db_session, seed_user.id, site_id="plasmodb", wdk_strategy_id=None
    )
    gene_set = await GeneSetService(get_gene_set_store()).create(
        user_id=seed_user.id,
        name="kinases",
        site_id="plasmodb",
        gene_ids=["PF3D7_0100100"],
        source="paste",
    )

    resp = await other_application_client.request(
        "DELETE", "/api/v1/user/data", params={"siteId": "plasmodb"}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "ok": True,
        "deleted": {
            "strategies": 0,
            "wdkStrategies": 0,
            "geneSets": 0,
            "experiments": 0,
            "controlSets": 0,
            "stagedEvalCases": 0,
        },
    }
    async with session_maker() as verify:
        survivor = await verify.get(Conversation, conversation)
        gene_set_row = await verify.get(GeneSetRow, gene_set.id)
    assert survivor is not None
    assert survivor.dismissed_at is None
    assert gene_set_row is not None
    assert gene_set.id in get_gene_set_store()._cache

    owner = await api_client.request(
        "DELETE", "/api/v1/user/data", params={"siteId": "plasmodb"}
    )

    assert owner.json()["deleted"] == {
        "strategies": 1,
        "wdkStrategies": 0,
        "geneSets": 1,
        "experiments": 0,
        "controlSets": 0,
        "stagedEvalCases": 0,
    }
    async with session_maker() as verify:
        purged = await verify.get(Conversation, conversation)
        assert purged is not None
        assert purged.dismissed_at is not None
        assert await verify.get(GeneSetRow, gene_set.id) is None
    assert gene_set.id not in get_gene_set_store()._cache


async def test_the_wdk_purge_deletes_only_the_strategies_its_own_chats_reference(
    api_client: httpx.AsyncClient,
    other_application_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    wdk_api: _FakeStrategyApi,
) -> None:
    """A strategy the caller never made is not the caller's to delete."""
    await _add_conv(db_session, seed_user.id, site_id=SITE, wdk_strategy_id=MINE)
    await _add_conv(
        db_session,
        seed_user.id,
        site_id=SITE,
        wdk_strategy_id=THEIRS,
        application_id=OTHER_APPLICATION_ID,
    )

    mine = await api_client.request(
        "DELETE",
        "/api/v1/user/data",
        params={"siteId": SITE, "deleteWdk": "true"},
    )

    assert mine.status_code == 200, mine.text
    assert wdk_api.deleted == [MINE]
    assert mine.json()["deleted"]["wdkStrategies"] == 1

    theirs = await other_application_client.request(
        "DELETE",
        "/api/v1/user/data",
        params={"siteId": SITE, "deleteWdk": "true"},
    )

    assert theirs.status_code == 200, theirs.text
    assert wdk_api.deleted == [MINE, THEIRS]
    assert theirs.json()["deleted"]["wdkStrategies"] == 1


async def test_a_saved_strategy_the_chat_only_imported_is_left_on_wdk(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    wdk_api: _FakeStrategyApi,
) -> None:
    """An imported saved strategy can be the user's own library work."""
    conversation = await _add_conv(
        db_session, seed_user.id, site_id=SITE, wdk_strategy_id=MINE
    )
    async with db_session.begin_nested():
        row = await db_session.get(Conversation, conversation)
        assert row is not None
        row.imported_saved_strategy_ids = [UNREFERENCED]
    await db_session.commit()

    resp = await api_client.request(
        "DELETE",
        "/api/v1/user/data",
        params={"siteId": SITE, "deleteWdk": "true"},
    )

    assert resp.status_code == 200, resp.text
    assert wdk_api.deleted == [MINE]


async def test_a_signed_out_purge_still_deletes_the_local_rows(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """The WDK half is refused without a VEuPathDB login; the local half is not.

    The strategy client is the real one, so the transport refuses the call
    before it reaches the network.
    """
    conversation = await _add_conv(
        db_session, seed_user.id, site_id=SITE, wdk_strategy_id=MINE
    )

    resp = await api_client.request(
        "DELETE",
        "/api/v1/user/data",
        params={"siteId": SITE, "deleteWdk": "true"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == {
        "strategies": 1,
        "wdkStrategies": 0,
        "geneSets": 0,
        "experiments": 0,
        "controlSets": 0,
        "stagedEvalCases": 0,
    }
    async with session_maker() as verify:
        assert await verify.get(Conversation, conversation) is None


async def test_purge_respects_site_scope(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    here = await _add_conv(
        db_session, seed_user.id, site_id="plasmodb", wdk_strategy_id=None
    )
    elsewhere = await _add_conv(
        db_session, seed_user.id, site_id="toxodb", wdk_strategy_id=None
    )

    resp = await api_client.request(
        "DELETE", "/api/v1/user/data", params={"siteId": "plasmodb"}
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"]["strategies"] == 1

    async with session_maker() as verify:
        rows = {
            c.id: c
            for c in (
                await verify.execute(
                    select(Conversation).where(Conversation.user_id == seed_user.id)
                )
            )
            .scalars()
            .all()
        }
    assert rows[here].dismissed_at is not None
    assert rows[elsewhere].dismissed_at is None
