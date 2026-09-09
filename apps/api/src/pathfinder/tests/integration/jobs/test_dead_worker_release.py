"""A job whose worker stopped sending a heartbeat fails on the next sweep.

The sweep runs every minute and the window is many beats of the heartbeat
thread. The started-age backstop is an hour wide, so a killed worker held its
lock and its stream open for an hour before this.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from assistant_core.conversation.event_writer import ChatEventWriter
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from procrastinate.testing import InMemoryConnector

from pathfinder.jobs.maintenance import release_stalled_jobs
from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests.integration.jobs._dead_worker import (
    TOOL_CALL_ID,
    dead_age,
    dead_window_seconds,
    fresh_beat_age,
    open_a_tool_call,
    stage_chat_turn_job,
    starved_age,
    turn_chunks,
)


async def _seed_conversation() -> tuple[UUID, UUID]:
    user_id = uuid4()
    conversation_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="killed worker",
            ),
        )
        await session.commit()
    return user_id, conversation_id


async def test_a_dead_workers_turn_fails_and_its_open_call_gets_an_error(
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id, conversation_id = await _seed_conversation()
    turn_id = uuid4()
    await open_a_tool_call(conversation_id, turn_id)
    job_id = await stage_chat_turn_job(
        in_memory_jobs,
        user_id=user_id,
        conversation_id=conversation_id,
        turn_id=turn_id,
        heartbeat_age_seconds=dead_age(),
    )

    await release_stalled_jobs()

    assert in_memory_jobs.jobs[job_id]["status"] == "failed"
    chunks = await turn_chunks(conversation_id)
    assert [chunk["type"] for chunk in chunks[-5:]] == [
        "tool-output-error",
        "error",
        "data-turn-failed",
        "finish",
        "done",
    ]
    assert chunks[-5]["toolCallId"] == TOOL_CALL_ID
    assert chunks[-5]["errorText"] == chunks[-4]["errorText"]
    assert "worker" in chunks[-4]["errorText"]
    assert "memory" in chunks[-4]["errorText"]


async def test_a_live_workers_job_is_left_alone(
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id, conversation_id = await _seed_conversation()
    turn_id = uuid4()
    await open_a_tool_call(conversation_id, turn_id)
    job_id = await stage_chat_turn_job(
        in_memory_jobs,
        user_id=user_id,
        conversation_id=conversation_id,
        turn_id=turn_id,
        heartbeat_age_seconds=fresh_beat_age(),
    )

    await release_stalled_jobs()

    assert in_memory_jobs.jobs[job_id]["status"] == "doing"
    assert [chunk["type"] for chunk in await turn_chunks(conversation_id)] == [
        "start",
        "tool-input-start",
        "tool-input-available",
    ]


async def test_a_starved_heartbeat_does_not_fail_a_running_turn(
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
) -> None:
    """A busy worker misses beats. The sweep leaves the window alone."""
    del patch_app_db_engine, db_cleaner
    user_id, conversation_id = await _seed_conversation()
    turn_id = uuid4()
    await open_a_tool_call(conversation_id, turn_id)
    starved = starved_age()
    assert 0 < starved < dead_window_seconds()
    job_id = await stage_chat_turn_job(
        in_memory_jobs,
        user_id=user_id,
        conversation_id=conversation_id,
        turn_id=turn_id,
        heartbeat_age_seconds=starved,
    )

    await release_stalled_jobs()

    assert in_memory_jobs.jobs[job_id]["status"] == "doing"
    assert [chunk["type"] for chunk in await turn_chunks(conversation_id)] == [
        "start",
        "tool-input-start",
        "tool-input-available",
    ]


async def test_a_closed_call_gets_no_second_error(
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id, conversation_id = await _seed_conversation()
    turn_id = uuid4()
    await open_a_tool_call(conversation_id, turn_id)
    writer = ChatEventWriter(conversation_id=conversation_id, turn_id=turn_id)
    await writer.write(
        {
            "type": "tool-output-available",
            "toolCallId": TOOL_CALL_ID,
            "output": {"studies": []},
        },
    )
    await stage_chat_turn_job(
        in_memory_jobs,
        user_id=user_id,
        conversation_id=conversation_id,
        turn_id=turn_id,
        heartbeat_age_seconds=dead_age(),
    )

    await release_stalled_jobs()

    chunks = await turn_chunks(conversation_id)
    assert [chunk["type"] for chunk in chunks[-4:]] == [
        "error",
        "data-turn-failed",
        "finish",
        "done",
    ]
    assert [chunk["type"] for chunk in chunks].count("tool-output-error") == 0
