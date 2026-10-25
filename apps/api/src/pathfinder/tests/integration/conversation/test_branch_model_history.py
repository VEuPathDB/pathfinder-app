"""What the model sees after a branch and after a revert.

F2 and R3 of the thread-surgery invariants: a turn on the branched or reverted
thread reads the history the anchor left, so it sees the pre-anchor tool calls
and none of the post-anchor ones.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform import db
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.fork import fork_conversation
from pathfinder.services.conversations.revert import revert_conversation_to_message
from pathfinder.tests.integration.conversation._turn_harness import (
    FIRST_LABEL,
    SECOND_LABEL,
    THIRD_LABEL,
    Recorder,
    assistant_message_ids,
    run_turn,
    seed_thread,
    silence_turn_runner,
    spec_for,
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


async def test_the_thread_carries_its_tool_calls_into_the_next_turn(
    patch_app_db_engine: None,
    db_cleaner: None,
    recorder: Recorder,
    saver: AsyncPostgresSaver,
) -> None:
    """The baseline the branch is measured against."""
    del patch_app_db_engine, db_cleaner
    spec = spec_for(recorder, saver)
    user_id, conversation_id = await seed_thread()

    await run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=FIRST_LABEL,
        spec=spec,
        saver=saver,
    )
    await run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=SECOND_LABEL,
        spec=spec,
        saver=saver,
    )

    assert recorder.labels_of_last_run() == [FIRST_LABEL, SECOND_LABEL]
    assert recorder.prompts_of_last_run() == [FIRST_LABEL, SECOND_LABEL]


async def test_f2_a_turn_on_a_branch_sees_the_anchor_s_history_and_no_more(
    patch_app_db_engine: None,
    db_cleaner: None,
    recorder: Recorder,
    saver: AsyncPostgresSaver,
) -> None:
    del patch_app_db_engine, db_cleaner
    spec = spec_for(recorder, saver)
    user_id, conversation_id = await seed_thread()
    first = await run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=FIRST_LABEL,
        spec=spec,
        saver=saver,
    )
    second_answer = await run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=SECOND_LABEL,
        spec=spec,
        saver=saver,
    )
    assert await assistant_message_ids(conversation_id) == [
        str(first.assistant_message_id),
        str(second_answer.assistant_message_id),
    ]

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=conversation_id,
            from_message_id=first.assistant_message_id,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    await run_turn(
        conversation_id=fork_id,
        user_id=user_id,
        text=THIRD_LABEL,
        spec=spec,
        saver=saver,
    )

    assert recorder.labels_of_last_run() == [FIRST_LABEL, THIRD_LABEL]
    assert recorder.prompts_of_last_run() == [FIRST_LABEL, THIRD_LABEL]
    assert SECOND_LABEL not in recorder.labels_of_last_run()


async def test_r3_a_turn_after_a_revert_sees_the_target_s_history_and_no_more(
    patch_app_db_engine: None,
    db_cleaner: None,
    recorder: Recorder,
    saver: AsyncPostgresSaver,
) -> None:
    del patch_app_db_engine, db_cleaner
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

    async with db.async_session_factory() as session:
        await revert_conversation_to_message(
            session,
            conversation_id=conversation_id,
            target_message_id=second.user_message_id,
            user_id=user_id,
        )
        await session.commit()

    await run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=THIRD_LABEL,
        spec=spec,
        saver=saver,
    )

    assert recorder.labels_of_last_run() == [FIRST_LABEL, THIRD_LABEL]
    assert recorder.prompts_of_last_run() == [FIRST_LABEL, THIRD_LABEL]
    assert SECOND_LABEL not in recorder.labels_of_last_run()
