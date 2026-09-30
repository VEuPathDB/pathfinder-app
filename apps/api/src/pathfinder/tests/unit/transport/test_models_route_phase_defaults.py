"""The models route answers the defaults this deployment's tier resolves to."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from pathfinder.platform.config import get_settings
from pathfinder.tests._support.models import (
    OPENAI_SMALL,
    OPENAI_STANDARD,
)
from pathfinder.transport.http.routers.models import router


async def _body() -> dict[str, Any]:
    app = FastAPI()
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/models")
    assert response.status_code == 200
    payload: dict[str, Any] = response.json()
    return payload


async def test_the_route_answers_the_models_the_tier_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A split tier moves the reasoning roles off the compile-time model."""
    settings = get_settings()
    monkeypatch.setattr(settings, "default_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "default_tier", "balanced", raising=False)

    body = await _body()

    assert body["defaultTier"] == "balanced"
    assert body["phaseDefaults"]["lead"] == OPENAI_STANDARD
    assert body["phaseDefaults"]["frame"] == OPENAI_STANDARD
    assert body["phaseDefaults"]["verification"] == OPENAI_SMALL
    assert body["phaseDefaults"]["execution"] == OPENAI_SMALL


async def test_the_route_answers_one_model_under_a_uniform_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "default_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "default_tier", "fast", raising=False)

    body = await _body()

    assert set(body["phaseDefaults"].values()) == {OPENAI_SMALL}
