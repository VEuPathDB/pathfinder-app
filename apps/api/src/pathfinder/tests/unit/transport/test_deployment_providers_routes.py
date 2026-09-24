"""The model list and the setup check read one set of providers the deployment pays for."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from pathfinder.platform.config import get_settings
from pathfinder.transport.http.routers.health import router as health_router
from pathfinder.transport.http.routers.models import router as models_router


@pytest.fixture
def _anthropic_only(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "default")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "deployment-anthropic")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "ollama_base_url", "")


async def _get(path: str) -> dict[str, Any]:
    app = FastAPI()
    app.include_router(models_router)
    app.include_router(health_router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


@pytest.mark.usefixtures("_anthropic_only")
async def test_a_model_is_enabled_where_the_deployment_holds_its_key() -> None:
    body = await _get("/api/v1/models")

    enabled = {m["provider"]: m["enabled"] for m in body["models"]}
    assert enabled == {
        "openai": False,
        "anthropic": True,
        "google": False,
        "ollama": False,
    }


async def test_the_mock_deployment_offers_every_model() -> None:
    body = await _get("/api/v1/models")

    assert {m["enabled"] for m in body["models"]} == {True}


@pytest.mark.usefixtures("_anthropic_only")
async def test_the_setup_check_names_the_same_providers() -> None:
    body = await _get("/health/config")

    assert body["llmConfigured"] is True
    assert body["providers"] == {
        "openai": False,
        "anthropic": True,
        "google": False,
        "ollama": False,
    }
