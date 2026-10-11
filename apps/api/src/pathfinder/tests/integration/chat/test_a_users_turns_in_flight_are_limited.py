from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Response
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.platform.security import limiter
from pathfinder.services.conversations import turn_slots
from pathfinder.tests.integration.chat._helpers import chat_post_body, chat_turn_jobs
from pathfinder.tests.integration.http.conftest import client_for
from pathfinder.transport.http.routers import chat


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb")
async def test_a_message_past_the_users_limit_is_refused_before_a_turn_is_queued(
    app: FastAPI,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _all_held(
        session: AsyncSession, *, user_id: UUID, other_than: UUID
    ) -> int:
        del session, user_id, other_than
        return 2

    monkeypatch.setattr(turn_slots, "turns_in_flight", _all_held)
    async with client_for(app, authed_user_id) as client:
        response = await client.post(
            "/api/v1/chat",
            json=chat_post_body(uuid4(), "count the kinases"),
            timeout=30.0,
        )

    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
    assert chat_turn_jobs(in_memory_jobs) == []


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb")
async def test_a_user_sends_at_most_twenty_messages_a_minute(
    app: FastAPI,
    authed_user_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _answered(**_kwargs: object) -> Response:
        return Response(status_code=200)

    monkeypatch.setattr(chat, "dispatch", _answered)
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    conversation_id = uuid4()
    async with client_for(app, authed_user_id) as client:
        statuses = [
            (
                await client.post(
                    "/api/v1/chat",
                    json=chat_post_body(conversation_id, "count the kinases"),
                    timeout=30.0,
                )
            ).status_code
            for _ in range(21)
        ]
    limiter.reset()

    assert statuses == [200] * 20 + [429]
