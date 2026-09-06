"""A revert leaves the strategy the surviving transcript describes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform import db
from sqlalchemy import text

from pathfinder.persistence.models import ConversationStrategy
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.revert import revert_conversation_to_message
from pathfinder.tests.integration.persistence._thread_surgery import (
    FOUR_STEPS,
    SOURCE_WDK_STRATEGY_ID,
    THREE_STEPS,
    add_assistant_message,
    add_user_message,
    install_fake_push,
    seed_conversation,
    seed_user,
    step_ids_of,
    write_strategy,
)


@pytest.fixture(scope="module", autouse=True)
async def _langgraph_checkpoint_tables(
    patch_app_db_engine: None,
) -> AsyncIterator[None]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield


@pytest.fixture(autouse=True)
async def _truncate_langgraph_tables() -> AsyncIterator[None]:
    yield
    async with db.async_session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE checkpoints, checkpoint_blobs, "
                "checkpoint_writes RESTART IDENTITY",
            ),
        )
        await session.commit()


async def _seed_thread() -> tuple[UUID, UUID]:
    user_id = await seed_user()
    return user_id, await seed_conversation(user_id)


async def test_revert_past_a_build_puts_the_strategy_back(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The card measured a four-step AST surviving the revert that deleted it."""
    del patch_app_db_engine, db_cleaner
    push = install_fake_push(monkeypatch)
    user_id, conversation_id = await _seed_thread()
    await add_user_message(conversation_id)
    await write_strategy(conversation_id, THREE_STEPS)
    await add_assistant_message(conversation_id)
    turn_three_user = await add_user_message(conversation_id)
    await write_strategy(conversation_id, FOUR_STEPS)
    await add_assistant_message(conversation_id)

    async with db.async_session_factory() as session:
        await revert_conversation_to_message(
            session,
            conversation_id=conversation_id,
            target_message_id=turn_three_user,
            user_id=user_id,
        )
        await session.commit()

    async with db.async_session_factory() as session:
        strategy = await session.get(ConversationStrategy, conversation_id)
        assert strategy is not None
        assert strategy.step_count == 3
        # The deleted turns may have moved the steps the snapshot names, so the
        # restored tree is pushed again and owns the ids WDK answered with.
        assert set(step_ids_of(strategy.strategy_ast)) == set(THREE_STEPS)
        assert set(step_ids_of(strategy.strategy_ast).values()).isdisjoint(
            THREE_STEPS.values(),
        )
        assert strategy.wdk_strategy_id == push.pushed_strategy_ids[0]
        assert strategy.wdk_strategy_id != SOURCE_WDK_STRATEGY_ID
        assert "stepCounts" not in strategy.strategy_ast
        latest = await StrategyRevisionRepository(session).latest(conversation_id)
        assert latest is not None
        assert latest.step_count == 3
        assert latest.wdk_strategy_id == push.pushed_strategy_ids[0]


async def test_revert_to_the_first_message_clears_a_strategy_built_after_it(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """No snapshot precedes the target, so the thread had no strategy then."""
    del patch_app_db_engine, db_cleaner
    user_id, conversation_id = await _seed_thread()
    first_user = await add_user_message(conversation_id)
    await write_strategy(conversation_id, THREE_STEPS)
    await add_assistant_message(conversation_id)

    async with db.async_session_factory() as session:
        await revert_conversation_to_message(
            session,
            conversation_id=conversation_id,
            target_message_id=first_user,
            user_id=user_id,
        )
        await session.commit()

    async with db.async_session_factory() as session:
        strategy = await session.get(ConversationStrategy, conversation_id)
        assert strategy is not None
        assert strategy.step_count == 0
        assert strategy.record_type is None
        assert strategy.wdk_strategy_id is None
        assert strategy.strategy_ast == {}


async def test_revert_leaves_a_thread_without_history_alone(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    """A thread built before the revision store keeps what it has."""
    del patch_app_db_engine, db_cleaner
    user_id, conversation_id = await _seed_thread()
    first_user = await add_user_message(conversation_id)
    await write_strategy(conversation_id, THREE_STEPS)
    await add_assistant_message(conversation_id)
    async with db.async_session_factory() as session:
        await StrategyRevisionRepository(session).delete_newer_than(
            conversation_id,
            revision_row_id=None,
        )
        await session.commit()

    async with db.async_session_factory() as session:
        await revert_conversation_to_message(
            session,
            conversation_id=conversation_id,
            target_message_id=first_user,
            user_id=user_id,
        )
        await session.commit()

    async with db.async_session_factory() as session:
        strategy = await session.get(ConversationStrategy, conversation_id)
        assert strategy is not None
        assert strategy.step_count == 3
