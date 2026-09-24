"""A key refused between dispatch and run ends the turn in the worker, before its graph."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import MonthlyUsage
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.domain.provider_keys import KeyRefusal
from pathfinder.platform.errors import ProviderKeyRefusedError
from pathfinder.platform.security import create_user_token
from pathfinder.services.provider_keys import record_refusals, store_key
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)

_KEY = "sk-proj-sentinel-0123456789WXYZ"
_DEADLOCK_CEILING_SECONDS = 120.0


@pytest.fixture
def _sealed(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with sealed_provider_keys(monkeypatch):
        yield


@pytest.mark.usefixtures("_sealed", "signed_in_to_veupathdb")
async def test_a_key_refused_after_dispatch_fails_the_turn_with_the_sentence(
    app: FastAPI,
    patch_app_db_engine: None,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    in_memory_jobs: InMemoryConnector,
) -> None:
    del patch_app_db_engine
    async with session_maker() as session:
        await store_key(session, authed_user_id, "openai", SecretStr(_KEY))
        await session.commit()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"pathfinder-auth": create_user_token(authed_user_id)},
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        post = asyncio.create_task(
            client.post(
                "/api/v1/chat",
                json=chat_post_body(uuid4(), "list the kinases"),
                timeout=_DEADLOCK_CEILING_SECONDS,
            ),
        )
        await asyncio.wait_for(
            wait_until_chat_turn_deferred(in_memory_jobs),
            timeout=_DEADLOCK_CEILING_SECONDS,
        )
        await record_refusals(authed_user_id, {"openai": KeyRefusal.INVALID})
        await run_deferred_chat_turns()
        response = await asyncio.wait_for(post, timeout=_DEADLOCK_CEILING_SECONDS)

    turn = [c for c in parse_sse_body(response.text) if c["type"] != "data-turn-status"]
    sentence = ProviderKeyRefusedError("OpenAI").detail
    assert [c["type"] for c in turn] == [
        "error",
        "data-turn-failed",
        "finish",
        "done",
    ]
    assert turn[0]["errorText"] == sentence
    assert turn[1]["data"]["errorText"] == sentence
    assert _KEY not in response.text
    async with session_maker() as session:
        spent = await session.scalar(select(func.count()).select_from(MonthlyUsage))
    assert spent == 0
