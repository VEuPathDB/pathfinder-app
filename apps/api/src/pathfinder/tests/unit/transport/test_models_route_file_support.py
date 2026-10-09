"""The models route says which files each model reads, so the composer offers
an attachment kind only to a model that reads it."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import FastAPI

from pathfinder.tests._support.models import DEFAULT_MODEL
from pathfinder.transport.http.routers.models import router


async def _models() -> dict[str, dict[str, Any]]:
    app = FastAPI()
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/models")
    assert response.status_code == 200
    return {m["id"]: m for m in response.json()["models"]}


async def test_each_model_carries_the_files_it_reads() -> None:
    models = await _models()

    reader = models[DEFAULT_MODEL]
    blind = models["mock:deterministic"]
    assert (reader["supportsImages"], reader["supportsDocuments"]) == (True, True)
    assert (blind["supportsImages"], blind["supportsDocuments"]) == (False, False)
