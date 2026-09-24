"""Rating an assistant message over HTTP: put, list, clear, and what is refused."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.memory.store import MemoryStore
from assistant_core.persistence.models import Conversation, Message
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import MessageRating, StrategyRevision
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.langfuse import actions
from pathfinder.tests.integration.http.conftest import client_for, make_user


@dataclass(frozen=True)
class _Thread:
    user_id: UUID
    conversation_id: UUID
    reply_id: UUID
    request_id: UUID


async def _thread(session: AsyncSession, user_id: UUID) -> _Thread:
    conversation = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=user_id,
        site_id="plasmodb",
        name="kinases",
    )
    session.add(conversation)
    await session.flush()
    request_id, reply_id = uuid4(), uuid4()
    session.add(
        Message(
            id=request_id,
            conversation_id=conversation.id,
            role="user",
            metadata_={},
        ),
    )
    session.add(
        Message(
            id=reply_id,
            conversation_id=conversation.id,
            role="assistant",
            metadata_={"usage": {"totalTokens": 18342, "costUsd": "0.0412"}},
        ),
    )
    await session.commit()
    return _Thread(user_id, conversation.id, reply_id, request_id)


@pytest.fixture
async def owner(
    db_session: AsyncSession,
    app_memory_store: MemoryStore,
) -> _Thread:
    del app_memory_store
    user = await make_user(db_session)
    return await _thread(db_session, user.id)


@pytest.fixture
async def client(
    app: FastAPI,
    patch_app_db_engine: None,
    owner: _Thread,
) -> AsyncGenerator[httpx.AsyncClient]:
    del patch_app_db_engine
    async with client_for(app, owner.user_id) as client:
        yield client


def _rating_url(thread: _Thread, message_id: UUID) -> str:
    return (
        f"/api/v1/conversations/{thread.conversation_id}/messages/{message_id}/rating"
    )


def _ratings(response: httpx.Response) -> list[dict[str, Any]]:
    assert response.status_code == 200
    body: list[dict[str, Any]] = response.json()["ratings"]
    return body


async def test_a_put_rates_the_message_and_the_list_carries_it(
    client: httpx.AsyncClient,
    owner: _Thread,
) -> None:
    put = await client.put(_rating_url(owner, owner.reply_id), json={"rating": "like"})

    assert put.status_code == 200
    assert put.json()["messageId"] == str(owner.reply_id)
    assert put.json()["rating"] == "like"
    assert put.json()["ratedAt"]
    listed = _ratings(
        await client.get(f"/api/v1/conversations/{owner.conversation_id}/ratings")
    )
    assert [(row["messageId"], row["rating"]) for row in listed] == [
        (str(owner.reply_id), "like")
    ]


async def test_a_delete_clears_the_rating_and_the_list_omits_it(
    client: httpx.AsyncClient,
    owner: _Thread,
) -> None:
    await client.put(_rating_url(owner, owner.reply_id), json={"rating": "dislike"})

    deleted = await client.delete(_rating_url(owner, owner.reply_id))

    assert deleted.status_code == 204
    listed = _ratings(
        await client.get(f"/api/v1/conversations/{owner.conversation_id}/ratings")
    )
    assert listed == []


async def test_a_delete_of_a_message_never_rated_is_204_and_writes_nothing(
    client: httpx.AsyncClient,
    owner: _Thread,
    db_session: AsyncSession,
) -> None:
    deleted = await client.delete(_rating_url(owner, owner.reply_id))

    assert deleted.status_code == 204
    rows = await db_session.scalar(select(func.count()).select_from(MessageRating))
    assert rows == 0


async def test_a_rating_is_reported_with_the_turn_s_usage(
    client: httpx.AsyncClient,
    owner: _Thread,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    langfuse = MagicMock()
    monkeypatch.setattr(actions, "get_langfuse", lambda: langfuse)

    await client.put(_rating_url(owner, owner.reply_id), json={"rating": "dislike"})
    await client.delete(_rating_url(owner, owner.reply_id))

    reported = [
        call.kwargs["metadata"] for call in langfuse.create_event.call_args_list
    ]
    assert [event["rating"] for event in reported] == ["dislike", "cleared"]
    assert reported[0]["messageId"] == str(owner.reply_id)
    assert reported[0]["conversationId"] == str(owner.conversation_id)
    assert reported[0]["totalTokens"] == 18342
    assert reported[0]["costUsd"] == 0.0412
    assert reported[0]["siteId"] == "plasmodb"


async def test_a_user_message_cannot_be_rated(
    client: httpx.AsyncClient,
    owner: _Thread,
) -> None:
    response = await client.put(
        _rating_url(owner, owner.request_id), json={"rating": "like"}
    )

    assert response.status_code == 404
    assert response.json()["title"] == "Message not found"


async def test_a_message_of_another_thread_cannot_be_rated_here(
    client: httpx.AsyncClient,
    owner: _Thread,
    db_session: AsyncSession,
) -> None:
    other = await _thread(db_session, owner.user_id)

    response = await client.put(
        _rating_url(owner, other.reply_id), json={"rating": "like"}
    )

    assert response.status_code == 404


async def test_an_unknown_message_is_404(
    client: httpx.AsyncClient,
    owner: _Thread,
) -> None:
    response = await client.put(_rating_url(owner, uuid4()), json={"rating": "like"})

    assert response.status_code == 404


async def test_a_rating_outside_the_two_values_is_422(
    client: httpx.AsyncClient,
    owner: _Thread,
) -> None:
    response = await client.put(
        _rating_url(owner, owner.reply_id), json={"rating": "neutral"}
    )

    assert response.status_code == 422


async def test_another_user_cannot_list_the_thread_s_ratings(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    owner: _Thread,
) -> None:
    del patch_app_db_engine
    intruder = await make_user(db_session)

    async with client_for(app, intruder.id) as client:
        response = await client.get(
            f"/api/v1/conversations/{owner.conversation_id}/ratings"
        )

    assert response.status_code == 404


async def test_a_dislike_of_a_turn_whose_strategy_does_not_parse_answers_200(
    client: httpx.AsyncClient,
    owner: _Thread,
    db_session: AsyncSession,
) -> None:
    db_session.add(
        StrategyRevision(
            conversation_id=owner.conversation_id,
            revision="r1-unparsed",
            record_type="transcript",
            strategy_ast={
                "recordType": "transcript",
                "description": "send the list to ada@example.org",
                "root": {"id": "step_a"},
            },
            step_count=1,
            message_id=owner.reply_id,
        ),
    )
    await db_session.commit()

    response = await client.put(
        _rating_url(owner, owner.reply_id), json={"rating": "dislike"}
    )

    assert response.status_code == 200
    assert response.json()["rating"] == "dislike"
