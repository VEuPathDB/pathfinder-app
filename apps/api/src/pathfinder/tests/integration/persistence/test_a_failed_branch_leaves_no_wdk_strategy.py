from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.persistence.models import Conversation
from assistant_core.platform import db
from sqlalchemy import func, select

from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.platform.config import get_settings
from pathfinder.services.conversations import fork
from pathfinder.services.conversations.service import ConversationService
from pathfinder.services.strategies import abandoned_mint
from pathfinder.tests.integration.persistence._thread_surgery import (
    FIRST_PUSHED_WDK_STRATEGY_ID,
    FakePush,
    FourTurns,
    four_turn_thread,
    install_fake_push,
    seed_user,
)
from pathfinder.tests.integration.services.strategies._mint_release import (
    FakeStrategyApi,
)

REFUSED = "the branch could not be written"


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


async def _refuse(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError(REFUSED)


async def _branches_of(conversation_id: UUID) -> int:
    async with db.async_session_factory() as session:
        return (
            await session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.parent_conversation_id == conversation_id),
            )
        ) or 0


async def _branch(thread: FourTurns, user_id: UUID) -> None:
    async with db.async_session_factory() as session:
        await fork.fork_conversation(
            session,
            source_conversation_id=thread.conversation_id,
            from_message_id=thread.answer_two,
            user_id=user_id,
        )
        await session.commit()


async def _thread(monkeypatch: pytest.MonkeyPatch) -> tuple[FourTurns, UUID, FakePush]:
    push = install_fake_push(monkeypatch)
    user_id = await seed_user()
    return await four_turn_thread(user_id), user_id, push


@pytest.mark.usefixtures("db_cleaner")
async def test_a_branch_whose_copy_fails_mints_nothing(
    monkeypatch: pytest.MonkeyPatch,
    site: FakeStrategyApi,
) -> None:
    thread, user_id, push = await _thread(monkeypatch)
    monkeypatch.setattr(fork, "branch_thread_binding", _refuse)

    with pytest.raises(RuntimeError, match=REFUSED):
        await _branch(thread, user_id)

    assert (push.pushed_strategy_ids, site.deleted) == ([], [])
    assert await _branches_of(thread.conversation_id) == 0


@pytest.mark.usefixtures("db_cleaner")
async def test_a_branch_whose_snapshot_write_fails_deletes_its_mint(
    monkeypatch: pytest.MonkeyPatch,
    site: FakeStrategyApi,
) -> None:
    thread, user_id, push = await _thread(monkeypatch)
    monkeypatch.setattr(StrategyRevisionRepository, "record", _refuse)

    with pytest.raises(RuntimeError, match=REFUSED):
        await _branch(thread, user_id)

    assert (push.pushed_strategy_ids, site.deleted) == (
        [FIRST_PUSHED_WDK_STRATEGY_ID],
        [FIRST_PUSHED_WDK_STRATEGY_ID],
    )
    assert await _branches_of(thread.conversation_id) == 0


@pytest.mark.usefixtures("db_cleaner")
async def test_a_branch_whose_commit_fails_deletes_its_mint(
    monkeypatch: pytest.MonkeyPatch,
    site: FakeStrategyApi,
) -> None:
    thread, user_id, push = await _thread(monkeypatch)

    async with db.async_session_factory() as session:
        monkeypatch.setattr(session, "commit", _refuse)
        with pytest.raises(RuntimeError, match=REFUSED):
            await ConversationService(session).fork(
                thread.conversation_id,
                user_id,
                thread.answer_two,
            )

    assert (push.pushed_strategy_ids, site.deleted) == (
        [FIRST_PUSHED_WDK_STRATEGY_ID],
        [FIRST_PUSHED_WDK_STRATEGY_ID],
    )
    assert await _branches_of(thread.conversation_id) == 0
