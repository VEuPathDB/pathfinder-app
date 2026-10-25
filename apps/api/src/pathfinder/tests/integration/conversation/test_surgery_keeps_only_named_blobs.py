from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.persistence.models import Message
from assistant_core.platform import db
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import select, text

from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.fork import fork_conversation
from pathfinder.services.conversations.revert import revert_conversation_to_message
from pathfinder.tests.integration.conversation._turn_harness import (
    FIRST_LABEL,
    SECOND_LABEL,
    THIRD_LABEL,
    Recorder,
    run_turn,
    seed_thread,
    silence_turn_runner,
    spec_for,
)

_BLOBS = text(
    "SELECT channel, version FROM checkpoint_blobs WHERE thread_id = :thread_id",
)
_NAMED_BEFORE = text(
    "SELECT DISTINCT named.key, named.value FROM checkpoints c, "
    "jsonb_each_text(c.checkpoint->'channel_versions') named "
    "JOIN checkpoint_blobs b ON b.channel = named.key AND b.version = named.value "
    "WHERE c.thread_id = :thread_id AND b.thread_id = c.thread_id "
    "AND b.checkpoint_ns = c.checkpoint_ns "
    "AND (c.checkpoint->>'ts')::timestamptz "
    "< COALESCE(CAST(:cutoff AS timestamptz), 'infinity'::timestamptz)",
)


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
async def saver(patch_app_db_engine: None) -> AsyncIterator[AsyncPostgresSaver]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url) as opened:
        yield opened


@pytest.fixture(autouse=True)
def _no_title_and_no_cancel_watch(monkeypatch: pytest.MonkeyPatch) -> None:
    silence_turn_runner(monkeypatch)


async def _blobs(thread_id: UUID) -> set[tuple[str, str]]:
    async with db.async_session_factory() as session:
        rows = await session.execute(_BLOBS, {"thread_id": str(thread_id)})
        return {(row.channel, row.version) for row in rows}


async def _named(thread_id: UUID, cutoff_message: UUID | None) -> set[tuple[str, str]]:
    async with db.async_session_factory() as session:
        cutoff = (
            None
            if cutoff_message is None
            else await session.scalar(
                select(Message.created_at).where(Message.id == cutoff_message),
            )
        )
        rows = await session.execute(
            _NAMED_BEFORE,
            {"thread_id": str(thread_id), "cutoff": cutoff},
        )
        return {(row.key, row.value) for row in rows}


@pytest.mark.usefixtures("db_cleaner")
async def test_f11_a_branch_copies_only_the_blobs_its_checkpoints_name(
    recorder: Recorder,
    saver: AsyncPostgresSaver,
) -> None:
    spec = spec_for(recorder, saver)
    user_id, conversation_id = await seed_thread()
    first = await run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=FIRST_LABEL,
        spec=spec,
        saver=saver,
    )
    second = await run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=SECOND_LABEL,
        spec=spec,
        saver=saver,
    )
    source_blobs = await _blobs(conversation_id)
    named_by_the_first_turn = await _named(conversation_id, second.user_message_id)

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=conversation_id,
            from_message_id=first.assistant_message_id,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    assert await _blobs(fork_id) == named_by_the_first_turn
    assert len(named_by_the_first_turn) < len(source_blobs)
    assert await _named(fork_id, None) == named_by_the_first_turn
    await run_turn(
        conversation_id=fork_id,
        user_id=user_id,
        text=THIRD_LABEL,
        spec=spec,
        saver=saver,
    )
    assert recorder.labels_of_last_run() == [FIRST_LABEL, THIRD_LABEL]


@pytest.mark.usefixtures("db_cleaner")
async def test_r9_a_revert_leaves_no_blob_its_checkpoints_do_not_name(
    recorder: Recorder,
    saver: AsyncPostgresSaver,
) -> None:
    spec = spec_for(recorder, saver)
    user_id, conversation_id = await seed_thread()
    await run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=FIRST_LABEL,
        spec=spec,
        saver=saver,
    )
    second = await run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=SECOND_LABEL,
        spec=spec,
        saver=saver,
    )
    before = await _blobs(conversation_id)
    surviving = await _named(conversation_id, second.user_message_id)

    async with db.async_session_factory() as session:
        await revert_conversation_to_message(
            session,
            conversation_id=conversation_id,
            target_message_id=second.user_message_id,
            user_id=user_id,
        )
        await session.commit()

    assert await _blobs(conversation_id) == surviving
    assert len(surviving) < len(before)
    await run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=THIRD_LABEL,
        spec=spec,
        saver=saver,
    )
    assert recorder.labels_of_last_run() == [FIRST_LABEL, THIRD_LABEL]
