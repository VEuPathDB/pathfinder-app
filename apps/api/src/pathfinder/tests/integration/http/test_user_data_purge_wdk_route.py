"""The VEuPathDB half of the purge: what a deleteWdk=true call destroys there."""

from __future__ import annotations

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.context import application_id_ctx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.errors import WDKError

from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services import user_data
from pathfinder.services.strategies.wdk_sync import ChatOwner, sync_to_chat
from pathfinder.tests.integration.http._user_data_purge import (
    MINE,
    OTHER_SITE,
    SITE,
    THEIRS,
    UNREFERENCED,
    FakeStrategyApi,
    add_conv,
    add_experiment,
    api_client,
    db_session,
    other_application_client,
    reading_api,
    seed_user,
    wdk_api,
)
from pathfinder.tests.integration.http.conftest import OTHER_APPLICATION_ID

__all__ = [
    "api_client",
    "db_session",
    "other_application_client",
    "seed_user",
    "wdk_api",
]


async def _purge(client: httpx.AsyncClient) -> httpx.Response:
    return await client.request(
        "DELETE",
        "/api/v1/user/data",
        params={"siteId": SITE, "deleteWdk": "true"},
    )


async def test_the_wdk_purge_deletes_only_the_strategies_its_own_chats_reference(
    api_client: httpx.AsyncClient,
    other_application_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    wdk_api: FakeStrategyApi,
) -> None:
    """A strategy the caller never made is not the caller's to delete."""
    await add_conv(
        db_session,
        seed_user.id,
        site_id=SITE,
        wdk_strategy_id=MINE,
        created_here=True,
    )
    await add_conv(
        db_session,
        seed_user.id,
        site_id=SITE,
        wdk_strategy_id=THEIRS,
        created_here=True,
        application_id=OTHER_APPLICATION_ID,
    )

    mine = await _purge(api_client)

    assert mine.status_code == 200, mine.text
    assert wdk_api.deleted == [MINE]
    assert mine.json()["deleted"]["wdkStrategies"] == 1

    theirs = await _purge(other_application_client)

    assert theirs.status_code == 200, theirs.text
    assert wdk_api.deleted == [MINE, THEIRS]
    assert theirs.json()["deleted"]["wdkStrategies"] == 1


async def test_a_strategy_opened_from_the_website_survives_the_wdk_purge(
    api_client: httpx.AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    wdk_api: FakeStrategyApi,
) -> None:
    """PathFinder destroys on VEuPathDB only what PathFinder made there."""
    token = application_id_ctx.set("pathfinder")
    try:
        async with session_maker() as session:
            await sync_to_chat(
                wdk_id=MINE,
                site_id=SITE,
                api=reading_api(),
                conv_repo=ConversationRepository(session),
                owner=ChatOwner(
                    user_id=seed_user.id,
                    assistant_id=PATHFINDER_ASSISTANT_ID,
                ),
                created_here=False,
            )
            await session.commit()
    finally:
        application_id_ctx.reset(token)

    resp = await _purge(api_client)

    assert resp.status_code == 200, resp.text
    assert wdk_api.deleted == []
    assert resp.json()["deleted"]["wdkStrategies"] == 0


async def test_a_saved_strategy_the_chat_only_imported_is_left_on_wdk(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    wdk_api: FakeStrategyApi,
) -> None:
    """An imported saved strategy can be the user's own library work."""
    conversation = await add_conv(
        db_session,
        seed_user.id,
        site_id=SITE,
        wdk_strategy_id=MINE,
        created_here=True,
    )
    async with db_session.begin_nested():
        row = await db_session.scalar(
            select(ConversationStrategy).where(
                ConversationStrategy.conversation_id == conversation,
            ),
        )
        assert row is not None
        row.imported_saved_strategy_ids = [UNREFERENCED]
    await db_session.commit()

    resp = await _purge(api_client)

    assert resp.status_code == 200, resp.text
    assert wdk_api.deleted == [MINE]


async def test_a_signed_out_purge_keeps_the_threads_it_could_not_finish(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A thread whose strategy still stands is dismissed, so a retry can finish.

    The strategy client is the real one, so the transport refuses the call
    before it reaches the network.
    """
    linked = await add_conv(
        db_session,
        seed_user.id,
        site_id=SITE,
        wdk_strategy_id=MINE,
        created_here=True,
    )
    unlinked = await add_conv(
        db_session,
        seed_user.id,
        site_id=SITE,
        wdk_strategy_id=None,
        created_here=False,
    )

    resp = await _purge(api_client)

    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == {
        "strategies": 2,
        "wdkStrategies": 0,
        "wdkStrategiesKept": 1,
        "memories": 0,
        "geneSets": 0,
        "experiments": 0,
        "controlSets": 0,
        "stagedEvalCases": 0,
    }
    async with session_maker() as verify:
        kept = await verify.get(Conversation, linked)
        assert await verify.get(Conversation, unlinked) is None
    assert kept is not None
    assert kept.dismissed_at is not None


async def test_a_site_that_answers_is_finished_and_one_that_does_not_is_kept(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reachable = FakeStrategyApi()

    def _api(site: str) -> FakeStrategyApi:
        if site == SITE:
            return reachable
        msg = f"{site} did not answer"
        raise WDKError(msg)

    monkeypatch.setattr(user_data, "get_strategy_api", _api)
    here = await add_conv(
        db_session,
        seed_user.id,
        site_id=SITE,
        wdk_strategy_id=MINE,
        created_here=True,
    )
    elsewhere = await add_conv(
        db_session,
        seed_user.id,
        site_id=OTHER_SITE,
        wdk_strategy_id=THEIRS,
        created_here=True,
    )

    resp = await api_client.request(
        "DELETE", "/api/v1/user/data", params={"deleteWdk": "true"}
    )

    assert resp.status_code == 200, resp.text
    assert reachable.deleted == [MINE]
    assert resp.json()["deleted"]["wdkStrategies"] == 1
    assert resp.json()["deleted"]["wdkStrategiesKept"] == 1
    async with session_maker() as verify:
        assert await verify.get(Conversation, here) is None
        kept = await verify.get(Conversation, elsewhere)
    assert kept is not None
    assert kept.dismissed_at is not None


async def test_repointing_a_thread_over_http_gives_up_the_claim(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    wdk_api: FakeStrategyApi,
) -> None:
    """An id handed in over HTTP was not minted by that thread."""
    conversation = await add_conv(
        db_session,
        seed_user.id,
        site_id=SITE,
        wdk_strategy_id=MINE,
        created_here=True,
    )

    patched = await api_client.patch(
        f"/api/v1/conversations/{conversation}",
        json={"wdkStrategyId": THEIRS},
    )
    assert patched.status_code == 200, patched.text

    resp = await _purge(api_client)

    assert resp.status_code == 200, resp.text
    assert wdk_api.deleted == []
    assert resp.json()["deleted"]["wdkStrategies"] == 0


async def test_the_purge_deletes_the_strategy_a_stored_run_created(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    wdk_api: FakeStrategyApi,
) -> None:
    """An experiment's persisted strategy is unambiguously PathFinder's."""
    await add_experiment(
        db_session, seed_user.id, site_id=SITE, wdk_strategy_id=UNREFERENCED
    )

    resp = await _purge(api_client)

    assert resp.status_code == 200, resp.text
    assert wdk_api.deleted == [UNREFERENCED]
    assert resp.json()["deleted"]["wdkStrategies"] == 1
    assert resp.json()["deleted"]["experiments"] == 1


async def test_repointing_a_thread_to_the_id_it_holds_keeps_the_claim(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    wdk_api: FakeStrategyApi,
) -> None:
    """A write that does not change the id does not change who made it."""
    conversation = await add_conv(
        db_session,
        seed_user.id,
        site_id=SITE,
        wdk_strategy_id=MINE,
        created_here=True,
    )

    patched = await api_client.patch(
        f"/api/v1/conversations/{conversation}",
        json={"wdkStrategyId": MINE},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["wdkStrategyCreatedHere"] is True

    resp = await _purge(api_client)

    assert resp.status_code == 200, resp.text
    assert wdk_api.deleted == [MINE]
    assert resp.json()["deleted"]["wdkStrategies"] == 1


async def test_the_next_purge_finishes_a_thread_the_first_one_only_dismissed(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    seed_user: User,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dismissed thread stays purgeable, so the retry deletes it for good."""
    reachable = FakeStrategyApi()
    answers = False

    def _api(site: str) -> FakeStrategyApi:
        if answers:
            return reachable
        msg = f"{site} did not answer"
        raise WDKError(msg)

    monkeypatch.setattr(user_data, "get_strategy_api", _api)
    conversation = await add_conv(
        db_session,
        seed_user.id,
        site_id=SITE,
        wdk_strategy_id=MINE,
        created_here=True,
    )

    first = await _purge(api_client)

    assert first.status_code == 200, first.text
    assert first.json()["deleted"]["wdkStrategies"] == 0
    assert first.json()["deleted"]["wdkStrategiesKept"] == 1
    async with session_maker() as verify:
        dismissed = await verify.get(Conversation, conversation)
    assert dismissed is not None
    assert dismissed.dismissed_at is not None

    answers = True
    second = await _purge(api_client)

    assert second.status_code == 200, second.text
    assert reachable.deleted == [MINE]
    assert second.json()["deleted"] == {
        "strategies": 1,
        "wdkStrategies": 1,
        "wdkStrategiesKept": 0,
        "memories": 0,
        "geneSets": 0,
        "experiments": 0,
        "controlSets": 0,
        "stagedEvalCases": 0,
    }
    async with session_maker() as verify:
        assert await verify.get(Conversation, conversation) is None
