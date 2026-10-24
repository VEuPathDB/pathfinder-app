from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from assistant_core.errors import ConversationNotFoundError
from assistant_core.platform import db
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncTransaction,
    create_async_engine,
)

from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import ErrorCode, ThreadBusyError
from pathfinder.services.conversations import thread_lock
from pathfinder.services.conversations.begin import refuse_a_thread_of_another_caller
from pathfinder.services.conversations.fork import ForkError, fork_conversation
from pathfinder.services.conversations.revert import (
    RevertError,
    revert_conversation_to_message,
)
from pathfinder.services.conversations.thread_lock import hold_thread
from pathfinder.tests.integration.persistence._thread_surgery import (
    four_turn_thread,
    seed_user,
)

_ADVISORY_LOCKS = text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'")
REFUSED = "the commit was refused"

pytestmark = pytest.mark.usefixtures("patch_app_db_engine")


async def _advisory_locks() -> int:
    async with db.async_session_factory() as session:
        return int((await session.execute(_ADVISORY_LOCKS)).scalar_one())


async def test_a_wait_past_the_deadline_is_refused() -> None:
    conversation_id = uuid4()
    async with hold_thread(conversation_id):
        with pytest.raises(ThreadBusyError) as refused:
            async with hold_thread(conversation_id, wait_seconds=0.3):
                pass

    assert (refused.value.code, refused.value.status, refused.value.detail) == (
        ErrorCode.SESSION_CONFLICT,
        409,
        "This chat is changing right now. Send the message again in a moment.",
    )
    assert await _advisory_locks() == 0


@pytest.fixture
async def pooled(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(get_settings().database_url, pool_size=1)
    monkeypatch.setattr(thread_lock, "get_engine", lambda: engine)
    yield engine
    await engine.dispose()


@pytest.mark.usefixtures("pooled")
async def test_a_task_cancelled_inside_the_hold_leaves_no_lock() -> None:
    conversation_id = uuid4()
    inside = asyncio.Event()

    async def _hold_forever() -> None:
        async with hold_thread(conversation_id):
            inside.set()
            await asyncio.Event().wait()

    holder = asyncio.create_task(_hold_forever())
    await inside.wait()
    held_inside = await _advisory_locks()
    holder.cancel()
    with pytest.raises(asyncio.CancelledError):
        await holder

    assert (held_inside, await _advisory_locks()) == (1, 0)
    async with hold_thread(conversation_id, wait_seconds=0.3):
        assert await _advisory_locks() == 1


async def test_a_release_that_fails_invalidates_the_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()
    invalidated: list[bool] = []
    invalidate = AsyncConnection.invalidate

    async def _refuse(self: AsyncTransaction) -> None:
        del self
        raise RuntimeError(REFUSED)

    async def _record(
        self: AsyncConnection, exception: BaseException | None = None
    ) -> None:
        invalidated.append(True)
        await invalidate(self, exception)

    monkeypatch.setattr(AsyncTransaction, "commit", _refuse)
    monkeypatch.setattr(AsyncConnection, "invalidate", _record)

    with pytest.raises(RuntimeError, match=REFUSED):
        async with hold_thread(conversation_id):
            pass

    monkeypatch.undo()
    assert invalidated == [True]
    assert await _advisory_locks() == 0


@pytest.mark.usefixtures("db_cleaner")
async def test_another_callers_thread_is_refused_before_its_lock() -> None:
    owner, stranger = await seed_user(), await seed_user()
    thread = await four_turn_thread(owner)

    async with hold_thread(thread.conversation_id):
        async with db.async_session_factory() as session:
            with pytest.raises(ConversationNotFoundError):
                await refuse_a_thread_of_another_caller(
                    session,
                    conversation_id=thread.conversation_id,
                    user_id=stranger,
                )
            with pytest.raises(ForkError):
                await fork_conversation(
                    session,
                    source_conversation_id=thread.conversation_id,
                    from_message_id=thread.answer_two,
                    user_id=stranger,
                )
            with pytest.raises(RevertError):
                await revert_conversation_to_message(
                    session,
                    conversation_id=thread.conversation_id,
                    target_message_id=thread.user_three,
                    user_id=stranger,
                )
            await refuse_a_thread_of_another_caller(
                session,
                conversation_id=thread.conversation_id,
                user_id=owner,
            )
            await refuse_a_thread_of_another_caller(
                session,
                conversation_id=uuid4(),
                user_id=stranger,
            )
        assert await _advisory_locks() == 1
