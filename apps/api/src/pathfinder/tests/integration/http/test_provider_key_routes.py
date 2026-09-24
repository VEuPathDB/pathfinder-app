"""A researcher enters a key once, reads back only its tail, and can remove it."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.provider_keys import KeyableProvider
from pathfinder.persistence.models import UserProviderKey
from pathfinder.platform.model_keys import KeyProbe, probe_key
from pathfinder.platform.security import limiter
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests._support.provider_wire import (
    ProviderWire,
    allow_requests_to_the_wire,
)
from pathfinder.tests.integration.http.conftest import (
    client_for,
    make_user,
    other_application_client_for,
)
from pathfinder.transport.http.routers.me import key_probe

_SENTINEL = "sk-proj-sentinel-0123456789WXYZ"
_KEYS = "/api/v1/me/provider-keys"


@pytest.fixture
def _sealed(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with sealed_provider_keys(monkeypatch):
        yield


def _probe_on(app: FastAPI, wire: ProviderWire) -> None:
    async def probe(provider: KeyableProvider, model_id: str, key: SecretStr) -> None:
        await probe_key(provider, model_id, key, wire.build)

    def with_wire() -> KeyProbe:
        return probe

    app.dependency_overrides[key_probe] = with_wire


async def _stored(session: AsyncSession) -> int:
    count = await session.scalar(select(func.count()).select_from(UserProviderKey))
    return int(count or 0)


@pytest.mark.usefixtures("_sealed")
async def test_a_key_the_provider_accepts_is_stored_and_never_sent_back(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    allow_requests_to_the_wire(monkeypatch)
    wire = ProviderWire()
    _probe_on(app, wire)
    user = await make_user(db_session)

    async with client_for(app, user.id) as client:
        put = await client.put(f"{_KEYS}/openai", json={"key": _SENTINEL})
        listed = await client.get(_KEYS)

    assert put.status_code == 200
    assert (put.json()["provider"], put.json()["hint"], put.json()["status"]) == (
        "openai",
        "WXYZ",
        "active",
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["enabled"] is True
    assert [(k["provider"], k["hint"]) for k in body["keys"]] == [("openai", "WXYZ")]
    assert body["payers"]["openai"] == "user"
    assert _SENTINEL not in put.text + listed.text
    assert [h["authorization"] for h in wire.sent_headers()] == [f"Bearer {_SENTINEL}"]


@pytest.mark.usefixtures("_sealed")
async def test_a_key_the_provider_refuses_is_not_stored(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    allow_requests_to_the_wire(monkeypatch)
    _probe_on(app, ProviderWire(refuse=True))
    user = await make_user(db_session)

    async with client_for(app, user.id) as client:
        response = await client.put(f"{_KEYS}/openai", json={"key": _SENTINEL})

    assert response.status_code == 422
    assert response.json()["code"] == "PROVIDER_KEY_REFUSED"
    assert _SENTINEL not in response.text
    assert "Incorrect API key" not in response.text
    assert await _stored(db_session) == 0


@pytest.mark.usefixtures("_sealed")
async def test_a_removed_key_is_gone_from_the_listing(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    allow_requests_to_the_wire(monkeypatch)
    _probe_on(app, ProviderWire())
    user = await make_user(db_session)

    async with client_for(app, user.id) as client:
        await client.put(f"{_KEYS}/openai", json={"key": _SENTINEL})
        removed = await client.delete(f"{_KEYS}/openai")
        listed = await client.get(_KEYS)

    assert removed.status_code == 204
    assert listed.json()["keys"] == []
    assert listed.json()["payers"]["openai"] == "deployment"


async def test_a_deployment_with_no_secret_refuses_a_key_before_the_probe(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    wire = ProviderWire()
    _probe_on(app, wire)
    user = await make_user(db_session)

    async with client_for(app, user.id) as client:
        response = await client.put(f"{_KEYS}/openai", json={"key": _SENTINEL})
        listed = await client.get(_KEYS)

    assert response.status_code == 403
    assert response.json()["code"] == "PROVIDER_KEYS_DISABLED"
    assert listed.json()["enabled"] is False
    assert wire.requests == []


async def test_a_short_key_is_refused_without_being_echoed(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user = await make_user(db_session)

    async with client_for(app, user.id) as client:
        response = await client.put(f"{_KEYS}/openai", json={"key": "sk-short"})
        ollama = await client.put(f"{_KEYS}/ollama", json={"key": _SENTINEL})

    assert response.status_code == 422
    assert "sk-short" not in response.text
    assert ollama.status_code == 422
    assert _SENTINEL not in ollama.text


@pytest.mark.usefixtures("_sealed", "other_application")
async def test_another_application_may_not_read_or_write_keys(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    user = await make_user(db_session)

    async with other_application_client_for(app, user.id) as client:
        listed = await client.get(_KEYS)
        put = await client.put(f"{_KEYS}/openai", json={"key": _SENTINEL})
        removed = await client.delete(f"{_KEYS}/openai")

    assert [listed.status_code, put.status_code, removed.status_code] == [403, 403, 403]
    assert await _stored(db_session) == 0


@pytest.mark.usefixtures("_sealed")
async def test_the_eleventh_key_in_an_hour_is_refused(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    allow_requests_to_the_wire(monkeypatch)
    _probe_on(app, ProviderWire())
    user = await make_user(db_session)
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()

    async with client_for(app, user.id) as client:
        statuses = [
            (await client.put(f"{_KEYS}/openai", json={"key": _SENTINEL})).status_code
            for _ in range(11)
        ]
    limiter.reset()

    assert statuses == [200] * 10 + [429]
