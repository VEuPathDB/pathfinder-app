from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.event_stream import replay_and_tail
from assistant_core.conversation.event_writer import ChatEventWriter
from assistant_core.persistence.models import Conversation
from assistant_core.platform import db

from pathfinder.persistence.models import User


async def _seed_conversation() -> tuple[UUID, UUID]:
    user_id = uuid4()
    conv_id = uuid4()
    turn_id = uuid4()
    async with db.async_session_factory() as session:
        session.add(User(id=user_id))
        session.add(
            Conversation(
                id=conv_id,
                user_id=user_id,
                site_id="plasmodb",
                name="t",
            ),
        )
        await session.commit()
    return conv_id, turn_id


@pytest.mark.asyncio
async def test_replay_returns_events_past_cursor(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    conv_id, turn_id = await _seed_conversation()
    writer = ChatEventWriter(conversation_id=conv_id, turn_id=turn_id)
    cursor = await writer.write({"type": "start"})
    held = await writer.write({"type": "text-start", "id": "a"})
    assert held == cursor
    id2 = await writer.write({"type": "text-delta", "id": "a", "delta": "x"})
    id3 = await writer.write({"type": "text-end", "id": "a"})

    collected: list[tuple[int, dict]] = []

    async def consume() -> None:
        async for event_id, chunk in replay_and_tail(
            conversation_id=conv_id,
            after=cursor,
        ):
            collected.append((event_id, chunk))
            if event_id >= id3:
                break

    await asyncio.wait_for(consume(), timeout=5)
    assert [e[0] for e in collected] == [id2 - 1, id2, id3]
    assert [e[1]["type"] for e in collected] == ["text-start", "text-delta", "text-end"]


@pytest.mark.asyncio
async def test_tail_yields_events_produced_after_subscribe(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    conv_id, turn_id = await _seed_conversation()
    writer = ChatEventWriter(conversation_id=conv_id, turn_id=turn_id)
    collected: list[tuple[int, dict]] = []

    async def consume() -> None:
        async for event_id, chunk in replay_and_tail(
            conversation_id=conv_id,
            after=0,
        ):
            collected.append((event_id, chunk))
            if len(collected) >= 3:
                break

    async def produce() -> None:
        await asyncio.sleep(0.3)
        await writer.write({"type": "text-start", "id": "a"})
        await writer.write({"type": "text-delta", "id": "a", "delta": "x"})
        await writer.write({"type": "text-end", "id": "a"})

    await asyncio.wait_for(
        asyncio.gather(consume(), produce()),
        timeout=10,
    )
    assert [c["type"] for _, c in collected] == [
        "text-start",
        "text-delta",
        "text-end",
    ]
