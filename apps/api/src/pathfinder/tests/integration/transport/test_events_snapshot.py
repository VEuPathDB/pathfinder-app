from __future__ import annotations

from uuid import uuid4

import httpx
from assistant_core.conversation.ui_message_reducer import user_message_chunk
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import User
from pathfinder.platform.security import create_user_token
from pathfinder.tests._support.chunk_log import reduce_chunks_to_messages

from ._events_snapshot_support import seed_chunks


async def test_snapshot_returns_empty_log_for_new_conversation(
    api_client: httpx.AsyncClient,
    conversation: Conversation,
) -> None:
    response = await api_client.get(
        f"/api/v1/conversations/{conversation.id}/events/snapshot",
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["chunks"] == []
    assert body["cursor"] == 0


async def test_snapshot_returns_full_chunk_log(
    api_client: httpx.AsyncClient,
    conversation: Conversation,
) -> None:
    user_id = uuid4()
    assistant_id = uuid4()
    seeded = [
        user_message_chunk(
            message_id=str(user_id),
            parts=[{"type": "text", "text": "what's the count?"}],
        ),
        {"type": "start", "messageId": str(assistant_id)},
        {"type": "text-start", "id": "t1"},
        {"type": "text-delta", "id": "t1", "delta": "the count is 42"},
        {"type": "text-end", "id": "t1"},
        {"type": "finish", "finishReason": "stop"},
        {"type": "done"},
    ]
    await seed_chunks(
        conversation_id=conversation.id,
        chunks=seeded,
    )
    response = await api_client.get(
        f"/api/v1/conversations/{conversation.id}/events/snapshot",
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cursor"] > 0
    assert len(body["chunks"]) == len(seeded)
    types = [c["type"] for c in body["chunks"]]
    assert types[0] == "user-message"
    assert types[-1] == "done"


async def test_snapshot_round_trips_through_reducer(
    api_client: httpx.AsyncClient,
    conversation: Conversation,
) -> None:
    user_id = uuid4()
    assistant_id = uuid4()
    seeded = [
        user_message_chunk(
            message_id=str(user_id),
            parts=[{"type": "text", "text": "ping"}],
        ),
        {"type": "start", "messageId": str(assistant_id)},
        {"type": "text-start", "id": "t1"},
        {"type": "text-delta", "id": "t1", "delta": "pong"},
        {"type": "text-end", "id": "t1"},
        {"type": "done"},
    ]
    await seed_chunks(
        conversation_id=conversation.id,
        chunks=seeded,
    )
    response = await api_client.get(
        f"/api/v1/conversations/{conversation.id}/events/snapshot",
    )
    body = response.json()
    messages = reduce_chunks_to_messages(body["chunks"])
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["id"] == str(user_id)
    assert messages[0]["parts"][0]["text"] == "ping"
    assert messages[1]["id"] == str(assistant_id)
    text_parts = [p for p in messages[1]["parts"] if p["type"] == "text"]
    assert text_parts[0]["text"] == "pong"


async def test_snapshot_caps_at_in_flight_user_message(
    api_client: httpx.AsyncClient,
    conversation: Conversation,
) -> None:
    user_a = uuid4()
    asst_a = uuid4()
    user_b = uuid4()
    asst_b = uuid4()
    seeded = [
        user_message_chunk(
            message_id=str(user_a),
            parts=[{"type": "text", "text": "first"}],
        ),
        {"type": "start", "messageId": str(asst_a)},
        {"type": "text-start", "id": "t1"},
        {"type": "text-delta", "id": "t1", "delta": "first reply"},
        {"type": "text-end", "id": "t1"},
        {"type": "done"},
        user_message_chunk(
            message_id=str(user_b),
            parts=[{"type": "text", "text": "second"}],
        ),
        {"type": "start", "messageId": str(asst_b)},
        {"type": "text-start", "id": "t2"},
        {"type": "text-delta", "id": "t2", "delta": "partial"},
    ]
    await seed_chunks(
        conversation_id=conversation.id,
        chunks=seeded,
    )
    response = await api_client.get(
        f"/api/v1/conversations/{conversation.id}/events/snapshot",
    )
    body = response.json()
    types = [c["type"] for c in body["chunks"]]
    assert types == [
        "user-message",
        "start",
        "text-start",
        "text-delta",
        "text-end",
        "done",
        "user-message",
    ]
    messages = reduce_chunks_to_messages(body["chunks"])
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[2]["id"] == str(user_b)


async def test_snapshot_ignores_rogue_mid_turn_user_message(
    api_client: httpx.AsyncClient,
    conversation: Conversation,
) -> None:
    user_a = uuid4()
    asst_a = uuid4()
    user_rogue = uuid4()
    seeded = [
        user_message_chunk(
            message_id=str(user_a),
            parts=[{"type": "text", "text": "kick off"}],
        ),
        {"type": "start", "messageId": str(asst_a)},
        {
            "type": "tool-input-start",
            "toolCallId": "call_X",
            "toolName": "do_thing",
        },
        {
            "type": "tool-input-delta",
            "toolCallId": "call_X",
            "inputTextDelta": "{",
        },
        user_message_chunk(
            message_id=str(user_rogue),
            parts=[{"type": "text", "text": "rogue mid-turn"}],
        ),
        {
            "type": "tool-input-delta",
            "toolCallId": "call_X",
            "inputTextDelta": "}",
        },
    ]
    await seed_chunks(
        conversation_id=conversation.id,
        chunks=seeded,
    )
    response = await api_client.get(
        f"/api/v1/conversations/{conversation.id}/events/snapshot",
    )
    body = response.json()
    types = [c["type"] for c in body["chunks"]]
    assert types == ["user-message"]
    assert body["chunks"][0]["message"]["id"] == str(user_a)


async def test_snapshot_404_for_other_users_conversation(
    app: FastAPI,
    db_session: AsyncSession,
    conversation: Conversation,
) -> None:
    other = User(id=uuid4())
    db_session.add(other)
    await db_session.flush()
    await db_session.commit()
    transport = httpx.ASGITransport(app=app)
    token = create_user_token(other.id)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"authorization": f"Bearer {token}"},
    ) as client:
        response = await client.get(
            f"/api/v1/conversations/{conversation.id}/events/snapshot",
        )
    assert response.status_code == 404
