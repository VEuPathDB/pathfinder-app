"""The tail streams only while a live worker holds the thread."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import httpx
from assistant_core.conversation.event_writer import ChatEventWriter
from assistant_core.conversation.ui_message_reducer import user_message_chunk
from assistant_core.graph.stream_events import turn_status_event
from assistant_core.persistence.models import Conversation
from assistant_core.platform import db
from assistant_core.tasks.chat_turn import defer_chat_turn
from sqlalchemy import text

from pathfinder.jobs.app import procrastinate_app
from pathfinder.tests._support.worker_heartbeat import (
    clear_workers,
    insert_worker_heartbeat,
)

_TAIL_CEILING_SECONDS = 10.0


async def _open_turn(conversation_id: UUID) -> ChatEventWriter:
    """Write the prompt and the queued status a dispatched turn leaves."""
    writer = ChatEventWriter(conversation_id=conversation_id, turn_id=uuid4())
    await writer.write(
        user_message_chunk(
            message_id=str(uuid4()),
            parts=[{"type": "text", "text": "count the kinases"}],
        ),
    )
    await writer.write(
        turn_status_event(label="Queued").model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        ),
    )
    return writer


async def _queue_turn_job(writer: ChatEventWriter) -> None:
    await defer_chat_turn(
        conversation_id=writer.conversation_id,
        payload={
            "turnId": str(writer.turn_id),
            "body": {"conversationId": str(writer.conversation_id)},
        },
    )


async def _take_job(conversation_id: UUID) -> None:
    """Move the thread's queued job to the state a worker running it has."""
    async with db.async_session_factory() as session:
        await session.execute(
            text(
                "UPDATE procrastinate_jobs SET status = 'doing' "
                "WHERE lock = :lock AND status = 'todo'",
            ),
            {"lock": str(conversation_id)},
        )
        await session.commit()


async def _tail(
    api_client: httpx.AsyncClient,
    conversation_id: UUID,
) -> httpx.Response:
    return await asyncio.wait_for(
        api_client.get(
            f"/api/v1/conversations/{conversation_id}/events",
            params={"after": "0"},
            timeout=_TAIL_CEILING_SECONDS,
        ),
        timeout=_TAIL_CEILING_SECONDS,
    )


async def _tail_until_done(
    api_client: httpx.AsyncClient,
    writer: ChatEventWriter,
) -> httpx.Response:
    """Tail the thread while a second task terminates the turn."""

    async def _finish() -> None:
        await asyncio.sleep(0.3)
        await writer.write({"type": "done"})

    finisher = asyncio.create_task(_finish())
    response = await _tail(api_client, writer.conversation_id)
    await finisher
    return response


async def test_a_tail_on_a_turn_no_job_holds_answers_204(
    patch_app_db_engine: None,
    api_client: httpx.AsyncClient,
    conversation: Conversation,
) -> None:
    """An open log whose job is gone is a dead turn, not a running one."""
    del patch_app_db_engine
    await _open_turn(conversation.id)
    await clear_workers()
    await insert_worker_heartbeat(age_seconds=2)

    response = await _tail(api_client, conversation.id)

    await clear_workers()
    assert response.status_code == 204


async def test_a_tail_on_a_job_no_worker_beats_for_answers_204(
    patch_app_db_engine: None,
    api_client: httpx.AsyncClient,
    conversation: Conversation,
) -> None:
    """A job procrastinate never released is not a turn anyone is writing."""
    del patch_app_db_engine
    writer = await _open_turn(conversation.id)
    await clear_workers()
    await insert_worker_heartbeat(age_seconds=600)

    async with procrastinate_app.open_async():
        await _queue_turn_job(writer)
        await _take_job(conversation.id)
        response = await _tail(api_client, conversation.id)

    await clear_workers()
    assert response.status_code == 204


async def test_a_tail_streams_while_the_turns_job_waits(
    patch_app_db_engine: None,
    api_client: httpx.AsyncClient,
    conversation: Conversation,
) -> None:
    """The same open log streams while its chat turn is still queued."""
    del patch_app_db_engine
    writer = await _open_turn(conversation.id)
    await clear_workers()
    await insert_worker_heartbeat(age_seconds=2)

    async with procrastinate_app.open_async():
        await _queue_turn_job(writer)
        response = await _tail_until_done(api_client, writer)

    await clear_workers()
    assert response.status_code == 200
    assert "[DONE]" in response.text


async def test_a_tail_streams_while_the_turns_job_runs(
    patch_app_db_engine: None,
    api_client: httpx.AsyncClient,
    conversation: Conversation,
) -> None:
    """A job a live worker has taken streams too, not only a queued one."""
    del patch_app_db_engine
    writer = await _open_turn(conversation.id)
    await clear_workers()
    await insert_worker_heartbeat(age_seconds=2)

    async with procrastinate_app.open_async():
        await _queue_turn_job(writer)
        await _take_job(conversation.id)
        response = await _tail_until_done(api_client, writer)

    await clear_workers()
    assert response.status_code == 200
    assert "[DONE]" in response.text


async def test_a_tail_on_a_finished_turn_answers_204(
    patch_app_db_engine: None,
    api_client: httpx.AsyncClient,
    conversation: Conversation,
) -> None:
    """A log the turn closed needs no tail, job or no job."""
    del patch_app_db_engine
    writer = await _open_turn(conversation.id)
    await writer.write({"type": "done"})
    await clear_workers()
    await insert_worker_heartbeat(age_seconds=2)

    async with procrastinate_app.open_async():
        await _queue_turn_job(writer)
        response = await _tail(api_client, conversation.id)

    await clear_workers()
    assert response.status_code == 204
