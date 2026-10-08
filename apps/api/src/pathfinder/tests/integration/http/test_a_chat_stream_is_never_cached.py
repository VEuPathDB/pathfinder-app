from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.tests.integration.http.conftest import (
    chat_body,
    client_for,
    ends_at_first_frame,
    make_user,
)


async def test_no_cache_or_proxy_holds_a_chat_turn_stream(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, in_memory_jobs, signed_in_to_veupathdb
    owner = await make_user(db_session)

    async with client_for(ends_at_first_frame(app), owner.id) as client:
        response = await client.post(
            "/api/v1/chat", json=chat_body(uuid4()), timeout=60.0
        )

    assert (response.status_code, response.headers["cache-control"]) == (
        200,
        "no-cache, no-transform",
    )
