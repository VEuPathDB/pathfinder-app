from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.persistence.models import Conversation
from assistant_core.platform import db
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs
from veupathdb.wdk import WDKStrategyDetails

from pathfinder.platform.config import get_settings
from pathfinder.services.conversations import surgery_commit
from pathfinder.services.conversations.service import ConversationService
from pathfinder.services.strategies import abandoned_mint
from pathfinder.tests.integration.persistence._failed_surgery import (
    REFUSED,
    refuse,
    thread_with_a_study,
)
from pathfinder.tests.integration.persistence._thread_surgery import (
    FIRST_PUSHED_WDK_STRATEGY_ID,
    four_turn_thread,
    install_fake_push,
    seed_user,
)
from pathfinder.tests.integration.services.strategies._mint_release import (
    FakeStrategyApi,
)
from pathfinder.transport.http.routers.conversations.revert import (
    RevertRequest,
    revert_to_message,
)

LOST = "the commit acknowledgement was lost"
ROLLBACK_LOST = "the connection was gone for the rollback"
UNREADABLE = "the saved mark came back unreadable"
pytestmark = pytest.mark.usefixtures("db_cleaner")


@pytest.fixture(scope="module", autouse=True)
async def _langgraph_checkpoint_tables(
    patch_app_db_engine: None,
) -> AsyncIterator[None]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> FakeStrategyApi:
    api = FakeStrategyApi()
    monkeypatch.setattr(abandoned_mint, "get_strategy_api", lambda _site: api)
    return api


def _lands_then_raises(session: AsyncSession) -> Callable[[], Awaitable[None]]:
    commit = session.commit

    async def _commit() -> None:
        await commit()
        raise ConnectionError(LOST)

    return _commit


async def _rollback_lost() -> None:
    raise ConnectionError(ROLLBACK_LOST)


async def _branches_of(thread_id: object) -> int:
    async with db.async_session_factory() as session:
        return (
            await session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.parent_conversation_id == thread_id),
            )
        ) or 0


async def test_a_branch_whose_commit_landed_keeps_what_it_made(
    monkeypatch: pytest.MonkeyPatch,
    site: FakeStrategyApi,
) -> None:
    thread, user_id, push, eda = await thread_with_a_study(monkeypatch)

    async with db.async_session_factory() as session:
        monkeypatch.setattr(session, "commit", _lands_then_raises(session))
        with pytest.raises(ConnectionError, match=LOST):
            await ConversationService(session).fork(
                thread.conversation_id,
                user_id,
                thread.answer_two,
            )

    assert (push.pushed_strategy_ids, site.deleted, eda.deleted) == (
        [FIRST_PUSHED_WDK_STRATEGY_ID],
        [],
        [],
    )
    assert await _branches_of(thread.conversation_id) == 1


async def test_a_revert_whose_commit_landed_keeps_its_mint(
    monkeypatch: pytest.MonkeyPatch,
    site: FakeStrategyApi,
) -> None:
    push = install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)

    async with db.async_session_factory() as session:
        monkeypatch.setattr(session, "commit", _lands_then_raises(session))
        with pytest.raises(ConnectionError, match=LOST):
            await revert_to_message(
                thread.conversation_id,
                RevertRequest(message_id=thread.user_three),
                session,
                user_id,
            )

    assert (push.pushed_strategy_ids, site.deleted) == (
        [FIRST_PUSHED_WDK_STRATEGY_ID],
        [],
    )


async def test_a_rollback_that_raises_still_releases_and_keeps_the_commit_error(
    monkeypatch: pytest.MonkeyPatch,
    site: FakeStrategyApi,
) -> None:
    thread, user_id, _, eda = await thread_with_a_study(monkeypatch)

    async with db.async_session_factory() as session:
        monkeypatch.setattr(session, "commit", refuse)
        monkeypatch.setattr(session, "rollback", _rollback_lost)
        with pytest.raises(RuntimeError, match=REFUSED):
            await ConversationService(session).fork(
                thread.conversation_id,
                user_id,
                thread.answer_two,
            )

    assert (site.deleted, eda.deleted) == ([FIRST_PUSHED_WDK_STRATEGY_ID], ["fresh1"])


async def test_both_releases_run_when_each_fails(
    monkeypatch: pytest.MonkeyPatch,
    site: FakeStrategyApi,
) -> None:
    thread, user_id, _, eda = await thread_with_a_study(monkeypatch)
    eda.refuse_delete = True

    async def _unreadable(strategy_id: int) -> WDKStrategyDetails:
        del strategy_id
        raise ValueError(UNREADABLE)

    monkeypatch.setattr(site, "get_strategy", _unreadable)

    async with db.async_session_factory() as session:
        monkeypatch.setattr(session, "commit", refuse)
        with capture_logs() as logs, pytest.raises(RuntimeError, match=REFUSED):
            await ConversationService(session).fork(
                thread.conversation_id,
                user_id,
                thread.answer_two,
            )

    assert eda.delete_attempts == ["fresh1"]
    assert [
        entry["event"] for entry in logs if entry["log_level"] in {"warning", "error"}
    ] == [
        "a release after a failed surgery raised",
        "kept an EDA document the surgery opened: the study service refused",
    ]


async def test_a_confirmation_that_hangs_keeps_what_the_surgery_made(
    monkeypatch: pytest.MonkeyPatch,
    site: FakeStrategyApi,
) -> None:
    thread, user_id, _, eda = await thread_with_a_study(monkeypatch)

    async def _hangs(*_args: object) -> bool:
        await asyncio.Event().wait()
        return False

    monkeypatch.setattr(surgery_commit, "a_projection_names", _hangs)
    monkeypatch.setattr(surgery_commit, "CONFIRM_SECONDS", 0.2)

    async with db.async_session_factory() as session:
        monkeypatch.setattr(session, "commit", refuse)
        with capture_logs() as logs, pytest.raises(RuntimeError, match=REFUSED):
            await asyncio.wait_for(
                ConversationService(session).fork(
                    thread.conversation_id,
                    user_id,
                    thread.answer_two,
                ),
                timeout=2.0,
            )

    assert (site.deleted, eda.deleted) == ([], [])
    assert "kept what a surgery made: its commit could not be confirmed" in [
        entry["event"] for entry in logs
    ]
    assert surgery_commit.CONFIRM_SECONDS == 0.2
