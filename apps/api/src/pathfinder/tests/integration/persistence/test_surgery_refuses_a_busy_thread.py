from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform import db
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import text

from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import (
    ErrorCode,
    ForkRefusedError,
    RevertRefusedError,
)
from pathfinder.services.conversations.fork import fork_conversation
from pathfinder.services.conversations.revert import revert_conversation_to_message
from pathfinder.services.conversations.thread_lock import (
    hold_thread,
    try_lock_thread,
)
from pathfinder.tests.integration.persistence._busy_thread import make_busy
from pathfinder.tests.integration.persistence._thread_surgery import (
    FourTurns,
    four_turn_thread,
    install_fake_push,
    message_ids,
    seed_user,
)

FORK_REFUSALS = {
    "queued turn": (
        "This chat is still answering. Branch it once the reply has finished."
    ),
    "running turn": (
        "This chat is still answering. Branch it once the reply has finished."
    ),
    "pending approval": (
        "This chat is waiting for your answer to a request. Answer it, then branch."
    ),
    "active task": (
        "This chat is running a background task. Branch it once the task has finished."
    ),
}
REVERT_REFUSALS = {
    "queued turn": (
        "This chat is still answering. Stop the reply or wait for it to finish, "
        "then undo."
    ),
    "running turn": (
        "This chat is still answering. Stop the reply or wait for it to finish, "
        "then undo."
    ),
    "pending approval": (
        "This chat is waiting for your answer to a request. Answer it, then undo."
    ),
    "active task": (
        "This chat is running a background task. Undo once the task has finished."
    ),
}
FORK_WHILE_LOCKED = "This chat is changing right now. Try the branch again in a moment."
REVERT_WHILE_LOCKED = "This chat is changing right now. Try the undo again in a moment."


@pytest.fixture
async def saver(patch_app_db_engine: None) -> AsyncIterator[AsyncPostgresSaver]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url) as opened:
        yield opened
    async with db.async_session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE checkpoints, checkpoint_blobs, "
                "checkpoint_writes, procrastinate_jobs CASCADE",
            ),
        )
        await session.commit()


async def _fork(thread: FourTurns, user_id: UUID) -> UUID:
    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=thread.conversation_id,
            from_message_id=thread.answer_two,
            user_id=user_id,
        )
        await session.commit()
        return fork.id


async def _revert(thread: FourTurns, user_id: UUID) -> None:
    async with db.async_session_factory() as session:
        await revert_conversation_to_message(
            session,
            conversation_id=thread.conversation_id,
            target_message_id=thread.user_three,
            user_id=user_id,
        )
        await session.commit()


@pytest.mark.parametrize("kind", sorted(FORK_REFUSALS))
@pytest.mark.usefixtures("db_cleaner")
async def test_a_branch_waits_for_the_thread_to_settle(
    kind: str,
    saver: AsyncPostgresSaver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    clear = await make_busy(
        kind,
        saver=saver,
        conversation_id=thread.conversation_id,
        user_id=user_id,
    )

    with pytest.raises(ForkRefusedError) as refused:
        await _fork(thread, user_id)

    assert (refused.value.code, refused.value.status, refused.value.detail) == (
        ErrorCode.FORK_REFUSED,
        409,
        FORK_REFUSALS[kind],
    )
    await clear()
    fork_id = await _fork(thread, user_id)
    assert len(await message_ids(fork_id)) == 2


@pytest.mark.parametrize("kind", sorted(REVERT_REFUSALS))
@pytest.mark.usefixtures("db_cleaner")
async def test_a_revert_waits_for_the_thread_to_settle(
    kind: str,
    saver: AsyncPostgresSaver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    clear = await make_busy(
        kind,
        saver=saver,
        conversation_id=thread.conversation_id,
        user_id=user_id,
    )
    before = await message_ids(thread.conversation_id)

    with pytest.raises(RevertRefusedError) as refused:
        await _revert(thread, user_id)

    assert (refused.value.code, refused.value.status, refused.value.detail) == (
        ErrorCode.REVERT_REFUSED,
        409,
        REVERT_REFUSALS[kind],
    )
    assert await message_ids(thread.conversation_id) == before
    await clear()
    await _revert(thread, user_id)
    assert await message_ids(thread.conversation_id) == [
        str(thread.user_one),
        str(thread.answer_two),
    ]


@pytest.mark.usefixtures("db_cleaner", "saver")
async def test_surgery_is_refused_while_a_turn_is_being_dispatched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)

    async with hold_thread(thread.conversation_id):
        with pytest.raises(ForkRefusedError) as fork_refused:
            await _fork(thread, user_id)
        with pytest.raises(RevertRefusedError) as revert_refused:
            await _revert(thread, user_id)

    assert fork_refused.value.detail == FORK_WHILE_LOCKED
    assert revert_refused.value.detail == REVERT_WHILE_LOCKED
    await _revert(thread, user_id)
    assert await message_ids(thread.conversation_id) == [
        str(thread.user_one),
        str(thread.answer_two),
    ]


async def _dispatch_into(conversation_id: UUID, entered: list[str]) -> None:
    async with hold_thread(conversation_id):
        entered.append("dispatch")


@pytest.mark.usefixtures("patch_app_db_engine")
async def test_a_dispatch_waits_for_a_surgery_to_commit() -> None:
    conversation_id = uuid4()
    entered: list[str] = []
    async with db.async_session_factory() as session:
        assert await try_lock_thread(session, conversation_id) is True
        dispatch = asyncio.create_task(_dispatch_into(conversation_id, entered))
        await asyncio.sleep(0.3)
        entered.append("surgery committed")
        await session.commit()

    await asyncio.wait_for(dispatch, timeout=5)
    assert entered == ["surgery committed", "dispatch"]
