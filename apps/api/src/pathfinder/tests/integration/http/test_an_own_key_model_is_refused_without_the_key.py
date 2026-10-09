from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from assistant_core.persistence.models import Message
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.services.provider_keys import store_key
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.http.conftest import (
    chat_body,
    chat_jobs,
    client_for,
    first_frame_client_for,
    make_user,
)

_OPUS = "anthropic:claude-opus-5-5"
_KEY = "sk-ant-sentinel-0123456789WXYZ"


@pytest.fixture
def _sealed(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with sealed_provider_keys(monkeypatch):
        yield


@pytest.mark.usefixtures("signed_in_to_veupathdb")
async def test_a_body_naming_opus_without_an_anthropic_key_is_refused(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del patch_app_db_engine, db_cleaner
    user = await make_user(db_session)
    body = {**chat_body(uuid4()), "phaseModels": {"lead": _OPUS}}

    async with client_for(app, user.id) as client:
        response = await client.post("/api/v1/chat", json=body)

    assert response.status_code == 422
    assert response.json()["code"] == "OWN_KEY_REQUIRED"
    messages = await db_session.scalar(select(func.count()).select_from(Message))
    assert (messages, chat_jobs(in_memory_jobs)) == (0, [])


@pytest.mark.usefixtures("_sealed", "signed_in_to_veupathdb")
async def test_a_body_naming_opus_on_the_researchers_anthropic_key_is_queued(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del patch_app_db_engine, db_cleaner
    user = await make_user(db_session)
    await store_key(db_session, user.id, "anthropic", SecretStr(_KEY))
    await db_session.commit()
    body = {**chat_body(uuid4()), "phaseModels": {"lead": _OPUS}}

    async with first_frame_client_for(app, user.id) as client:
        response = await client.post("/api/v1/chat", json=body)

    assert response.status_code == 200
    assert len(chat_jobs(in_memory_jobs)) == 1
