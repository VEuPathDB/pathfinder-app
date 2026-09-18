"""A branch reproduces the thread as it stood at the branched message."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.persistence.models import (
    BackgroundTask,
    Conversation,
    ConversationEvent,
    Message,
)
from assistant_core.platform import db
from sqlalchemy import delete, select, text

from pathfinder.persistence.models import (
    ConversationStrategy,
    StrategyRevision,
)
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import ErrorCode, ForkRefusedError
from pathfinder.services.conversations.fork import ForkError, fork_conversation
from pathfinder.services.conversations.revert import revert_conversation_to_message
from pathfinder.tests.integration.persistence._thread_surgery import (
    FIRST_PUSHED_WDK_STRATEGY_ID,
    THREE_STEPS,
    add_assistant_message,
    event_count,
    four_turn_thread,
    install_fake_push,
    message_ids_in,
    seed_conversation,
    seed_user,
    step_ids_of,
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


async def test_branch_at_turn_two_gets_the_three_step_tree_and_a_new_wdk_id(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The card's measurement: the branch showed 4 steps and root 16."""
    del patch_app_db_engine, db_cleaner
    push = install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=thread.conversation_id,
            from_message_id=thread.answer_two,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    assert step_ids_of(push.seen[0]) == THREE_STEPS
    async with db.async_session_factory() as session:
        strategy = await session.get(ConversationStrategy, fork_id)
        assert strategy is not None
        assert strategy.step_count == 3
        assert strategy.wdk_strategy_id == FIRST_PUSHED_WDK_STRATEGY_ID
        assert strategy.wdk_strategy_created_here is True
        assert "orthologs" not in step_ids_of(strategy.strategy_ast)


async def test_branch_before_the_build_has_no_strategy(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    push = install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=thread.conversation_id,
            from_message_id=thread.user_one,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    assert push.seen == []
    async with db.async_session_factory() as session:
        assert await session.get(ConversationStrategy, fork_id) is None


async def test_branch_of_a_thread_with_no_history_is_refused(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A thread built before the revision store cannot be reproduced."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    async with db.async_session_factory() as session:
        await session.execute(
            delete(StrategyRevision).where(
                StrategyRevision.conversation_id == thread.conversation_id,
            ),
        )
        await session.commit()

    async with db.async_session_factory() as session:
        with pytest.raises(ForkRefusedError) as excinfo:
            await fork_conversation(
                session,
                source_conversation_id=thread.conversation_id,
                from_message_id=thread.answer_two,
                user_id=user_id,
            )
    assert excinfo.value.code is ErrorCode.FORK_REFUSED
    assert excinfo.value.status == 409


async def test_branch_is_refused_while_a_durable_task_runs(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    async with db.async_session_factory() as session:
        session.add(
            BackgroundTask(
                id=uuid4(),
                conversation_id=thread.conversation_id,
                user_id=user_id,
                tool_name="run_eda_compute",
                status="running",
            ),
        )
        await session.commit()

    async with db.async_session_factory() as session:
        with pytest.raises(ForkRefusedError):
            await fork_conversation(
                session,
                source_conversation_id=thread.conversation_id,
                from_message_id=thread.answer_four,
                user_id=user_id,
            )


async def test_a_branch_carries_no_parent_message_id_and_reverts_in_place(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The card's 404: the branch replayed the parent's ids."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    parent_ids = {
        str(thread.user_one),
        str(thread.answer_two),
        str(thread.user_three),
        str(thread.answer_four),
    }

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=thread.conversation_id,
            from_message_id=thread.answer_two,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(ConversationEvent).where(
                        ConversationEvent.conversation_id == fork_id,
                    ),
                )
            )
            .scalars()
            .all()
        )
        chunk_ids: set[str] = set()
        for row in rows:
            chunk_ids |= message_ids_in(row.chunk)
        fork_message_ids = {
            str(mid)
            for mid in (
                await session.execute(
                    select(Message.id).where(Message.conversation_id == fork_id),
                )
            ).scalars()
        }
    assert chunk_ids
    assert chunk_ids & parent_ids == set()
    assert chunk_ids <= fork_message_ids

    branch_user_message = next(mid for mid in chunk_ids if mid in fork_message_ids)
    async with db.async_session_factory() as session:
        target = await session.scalar(
            select(Message).where(
                Message.conversation_id == fork_id,
                Message.role == "user",
            ),
        )
        assert target is not None
        await revert_conversation_to_message(
            session,
            conversation_id=fork_id,
            target_message_id=target.id,
            user_id=user_id,
        )
        await session.commit()
    assert branch_user_message in fork_message_ids


async def test_a_fork_log_survives_a_parent_revert_and_delete(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The card's 5 -> 4: the parent's task row took the fork's chunk."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    task_id = uuid4()
    async with db.async_session_factory() as session:
        session.add(
            BackgroundTask(
                id=task_id,
                conversation_id=thread.conversation_id,
                user_id=user_id,
                tool_name="run_eda_compute",
                status="complete",
            ),
        )
        await session.flush()
        session.add(
            ConversationEvent(
                conversation_id=thread.conversation_id,
                task_id=task_id,
                chunk={"type": "data-task-progress", "data": {"percent": 50}},
            ),
        )
        await session.commit()

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=thread.conversation_id,
            from_message_id=thread.answer_four,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    before = await event_count(fork_id)
    assert before > 0

    async with db.async_session_factory() as session:
        await revert_conversation_to_message(
            session,
            conversation_id=thread.conversation_id,
            target_message_id=thread.user_three,
            user_id=user_id,
        )
        await session.commit()
    assert await event_count(fork_id) == before

    async with db.async_session_factory() as session:
        await ConversationRepository(session).delete(thread.conversation_id)
        await session.commit()
    assert await event_count(fork_id) == before


async def test_a_branch_of_a_site_help_thread_stays_site_help(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    conversation_id = await seed_conversation(user_id, assistant_id="site_help")
    anchor = await add_assistant_message(conversation_id)

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=conversation_id,
            from_message_id=anchor,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    async with db.async_session_factory() as session:
        source = await session.get(Conversation, conversation_id)
        branch = await session.get(Conversation, fork_id)
        assert source is not None
        assert branch is not None
        assert branch.assistant_id == "site_help"
        assert branch.application_id == source.application_id


async def test_fork_still_rejects_an_anchor_from_another_thread(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    conversation_id = await seed_conversation(user_id)
    async with db.async_session_factory() as session:
        with pytest.raises(ForkError):
            await fork_conversation(
                session,
                source_conversation_id=conversation_id,
                from_message_id=uuid4(),
                user_id=user_id,
            )
