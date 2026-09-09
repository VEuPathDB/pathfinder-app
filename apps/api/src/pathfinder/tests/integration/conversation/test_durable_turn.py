"""Tests the full chat turn cycle, from the post to the worker to the event stream."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import httpx
from assistant_core.conversation.event_writer import ChatEventWriter
from assistant_core.persistence.models import Conversation
from assistant_core.platform import db
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.jobs.app import procrastinate_app
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.security import create_user_token

# A ceiling on a hung request, not a budget for a fast one: every hop is
# in-process against the mock provider and settles in under a second, so a
# wait near this bound is a deadlock and not a loaded machine.
_DEADLOCK_CEILING_SECONDS = 120.0


def _event_ids(body: str) -> list[int]:
    return [
        int(line.split(":", 1)[1].strip())
        for line in body.splitlines()
        if line.startswith("id:")
    ]


async def _drain() -> None:
    """Runs every queued chat turn job in this process."""
    async with procrastinate_app.open_async():
        await procrastinate_app.run_worker_async(
            queues=["chat_turn"],
            wait=False,
            listen_notify=False,
            install_signal_handlers=False,
        )


async def _wait_until_enqueued(connector: InMemoryConnector) -> None:
    """Waits until the request has queued a chat turn job.

    A drain that starts before the job exists returns at once, so the caller
    must wait here. The caller must also bound the wait with a timeout.
    """
    while True:
        if any(j["task_name"] == "chat_turn:run" for j in connector.jobs.values()):
            return
        await asyncio.sleep(0.02)


def _post_body(conv_id: UUID) -> dict:
    msg_id = str(uuid4())
    return {
        "trigger": "submit-message",
        "id": msg_id,
        "messages": [
            {
                "id": msg_id,
                "role": "user",
                "parts": [{"type": "text", "text": "hi"}],
            },
        ],
        "conversationId": str(conv_id),
        "siteId": "plasmodb",
    }


async def _seed_conversation(user_id: UUID) -> UUID:
    """Inserts a conversation row for a user that already exists."""
    conv_id = uuid4()
    async with db.async_session_factory() as session:
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conv_id,
                user_id=user_id,
                site_id="plasmodb",
                name="t",
            ),
        )
        await session.commit()
    return conv_id


async def test_post_chat_enqueues_runs_and_streams_until_done(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    conv_id = uuid4()
    token = create_user_token(authed_user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"pathfinder-auth": token},
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        post_task = asyncio.create_task(
            client.post(
                "/api/v1/chat",
                json=_post_body(conv_id),
                timeout=_DEADLOCK_CEILING_SECONDS,
            ),
        )
        await asyncio.wait_for(
            _wait_until_enqueued(in_memory_jobs), timeout=_DEADLOCK_CEILING_SECONDS
        )
        await _drain()
        post_res = await asyncio.wait_for(post_task, timeout=_DEADLOCK_CEILING_SECONDS)

    assert post_res.status_code == 200
    body = post_res.text
    assert "[DONE]" in body
    assert body.count("data:") >= 3


async def test_post_chat_does_not_replay_prior_turn_events(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    """A new turn streams only its own events, never the events of an earlier turn."""
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    conv_id = await _seed_conversation(authed_user_id)
    prior_writer = ChatEventWriter(
        conversation_id=conv_id,
        turn_id=uuid4(),
    )
    await prior_writer.write({"type": "start", "messageId": "prior"})
    await prior_writer.write({"type": "text-start", "id": "a"})
    await prior_writer.write({"type": "text-delta", "id": "a", "delta": "old"})
    prior_done_id = await prior_writer.write({"type": "done"})

    token = create_user_token(authed_user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"pathfinder-auth": token},
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        post_task = asyncio.create_task(
            client.post(
                "/api/v1/chat",
                json=_post_body(conv_id),
                timeout=_DEADLOCK_CEILING_SECONDS,
            ),
        )
        await asyncio.wait_for(
            _wait_until_enqueued(in_memory_jobs), timeout=_DEADLOCK_CEILING_SECONDS
        )
        await _drain()
        post_res = await asyncio.wait_for(post_task, timeout=_DEADLOCK_CEILING_SECONDS)

    assert post_res.status_code == 200
    ids = _event_ids(post_res.text)
    assert len(ids) >= 1
    assert all(i > prior_done_id for i in ids), (
        f"POST replayed prior events (ids ≤ {prior_done_id}): {ids}"
    )


async def test_events_endpoint_returns_204_when_turn_complete(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    """The events endpoint returns no content when the last event is a done chunk."""
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    conv_id = uuid4()
    token = create_user_token(authed_user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"pathfinder-auth": token},
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        post_task = asyncio.create_task(
            client.post(
                "/api/v1/chat",
                json=_post_body(conv_id),
                timeout=_DEADLOCK_CEILING_SECONDS,
            ),
        )
        await asyncio.wait_for(
            _wait_until_enqueued(in_memory_jobs), timeout=_DEADLOCK_CEILING_SECONDS
        )
        await _drain()
        post_res = await asyncio.wait_for(post_task, timeout=_DEADLOCK_CEILING_SECONDS)
        assert post_res.status_code == 200

        get_res = await client.get(
            f"/api/v1/conversations/{conv_id}/events",
            params={"after": "0"},
            timeout=_DEADLOCK_CEILING_SECONDS,
        )

    assert get_res.status_code == 204


async def test_events_endpoint_returns_204_on_empty_conversation(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    authed_user_id: UUID,
) -> None:
    """A conversation with zero events has nothing to resume."""
    del patch_app_db_engine, db_cleaner
    conv_id = await _seed_conversation(authed_user_id)
    token = create_user_token(authed_user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"pathfinder-auth": token},
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        res = await client.get(
            f"/api/v1/conversations/{conv_id}/events",
            params={"after": "0"},
            timeout=_DEADLOCK_CEILING_SECONDS,
        )

    assert res.status_code == 204


async def test_events_endpoint_streams_when_last_event_is_not_done(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    authed_user_id: UUID,
) -> None:
    """The events endpoint streams while the last event is not a done chunk."""
    del patch_app_db_engine, db_cleaner
    conv_id = await _seed_conversation(authed_user_id)
    writer = ChatEventWriter(conversation_id=conv_id, turn_id=uuid4())
    await writer.write({"type": "start", "messageId": "live"})
    await writer.write({"type": "text-start", "id": "a"})
    await writer.write({"type": "text-delta", "id": "a", "delta": "x"})
    token = create_user_token(authed_user_id)

    async def _finisher() -> None:
        await asyncio.sleep(0.3)
        await writer.write({"type": "text-end", "id": "a"})
        await writer.write({"type": "done"})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"pathfinder-auth": token},
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        finisher_task = asyncio.create_task(_finisher())
        res = await client.get(
            f"/api/v1/conversations/{conv_id}/events",
            params={"after": "0"},
            timeout=_DEADLOCK_CEILING_SECONDS,
        )
        await finisher_task

    assert res.status_code == 200
    assert "[DONE]" in res.text
    assert res.text.count("data:") >= 4


async def test_two_concurrent_subscribers_consistent_204_when_complete(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    """Two subscribers that connect after the turn ends both get no content."""
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    conv_id = uuid4()
    token = create_user_token(authed_user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"pathfinder-auth": token},
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        post_task = asyncio.create_task(
            client.post(
                "/api/v1/chat",
                json=_post_body(conv_id),
                timeout=_DEADLOCK_CEILING_SECONDS,
            ),
        )
        await asyncio.wait_for(
            _wait_until_enqueued(in_memory_jobs), timeout=_DEADLOCK_CEILING_SECONDS
        )
        await _drain()
        post_res = await asyncio.wait_for(post_task, timeout=_DEADLOCK_CEILING_SECONDS)
        assert post_res.status_code == 200

        res_a, res_b = await asyncio.gather(
            client.get(
                f"/api/v1/conversations/{conv_id}/events",
                params={"after": "0"},
                timeout=_DEADLOCK_CEILING_SECONDS,
            ),
            client.get(
                f"/api/v1/conversations/{conv_id}/events",
                params={"after": "0"},
                timeout=_DEADLOCK_CEILING_SECONDS,
            ),
        )

    assert res_a.status_code == 204
    assert res_b.status_code == 204
