from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.assistants import registry
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import AUDIT_ASSISTANT_ID
from pathfinder.services.provider_keys import store_key
from pathfinder.tests._support.models import ANTHROPIC_SMALL, DEFAULT_MODEL
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import client_for, make_user

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb"
)


@pytest.fixture
def review_on_an_unpaid_provider(
    monkeypatch: pytest.MonkeyPatch,
    app: FastAPI,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
) -> Iterator[None]:
    del app, db_session, in_memory_jobs
    with sealed_provider_keys(monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "pathfinder_chat_provider", "default")
        monkeypatch.setattr(settings, "default_tier", "custom")
        monkeypatch.setattr(settings, "input_screening_enabled", False)
        monkeypatch.setattr(
            registry,
            "audit_compile_time_models",
            lambda: {"auditor": DEFAULT_MODEL, "audit_review": ANTHROPIC_SMALL},
        )
        yield


async def _deferred_or_refused(
    app: FastAPI, user_id: UUID, connector: InMemoryConnector, body: dict[str, Any]
) -> str:
    async with client_for(app, user_id) as client:
        posted = asyncio.create_task(client.post("/api/v1/chat", json=body))
        waited = asyncio.create_task(wait_until_chat_turn_deferred(connector))
        done, _ = await asyncio.wait(
            {posted, waited}, timeout=10.0, return_when=asyncio.FIRST_COMPLETED
        )
        posted.cancel()
        waited.cancel()
    if waited in done:
        return "deferred"
    if posted in done:
        return f"refused {posted.result().status_code}"
    return "neither"


@pytest.mark.usefixtures("review_on_an_unpaid_provider")
async def test_an_audit_turn_is_answered_when_only_the_review_has_no_payer(
    app: FastAPI, db_session: AsyncSession, in_memory_jobs: InMemoryConnector
) -> None:
    owner = await make_user(db_session)
    await store_key(
        db_session, owner.id, "openai", SecretStr("sk-proj-sentinel-0123456789WXYZ")
    )
    await db_session.commit()
    body = chat_post_body(uuid4(), "hello")
    body["assistantId"] = AUDIT_ASSISTANT_ID

    outcome = await _deferred_or_refused(app, owner.id, in_memory_jobs, body)

    assert outcome == "deferred"
