"""The models route overlays the live price snapshot on the catalog entry.

``claude-haiku-4-5`` is the pinned pair: its snapshot price carries no dated
constraint, so the route's undated lookup answers the same number at any
instant.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from assistant_core.pricing import lookup_per_mtok_prices
from fastapi import FastAPI

from pathfinder.platform.model_catalog import ModelEntry
from pathfinder.transport.http.routers import models
from pathfinder.transport.http.routers.models import router

HAIKU = "anthropic:claude-haiku-4-5"


async def _models() -> list[dict[str, Any]]:
    app = FastAPI()
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/models")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    served: list[dict[str, Any]] = body["models"]
    return served


def _serve(monkeypatch: pytest.MonkeyPatch, *entries: ModelEntry) -> None:
    monkeypatch.setattr(models, "get_model_catalog", lambda: entries)


def test_the_pinned_pair_prices_the_same_at_any_instant() -> None:
    """The pinned model's snapshot price holds with no dated constraint."""
    early = lookup_per_mtok_prices(
        "anthropic", "claude-haiku-4-5", at=datetime(2024, 1, 1, tzinfo=UTC)
    )
    late = lookup_per_mtok_prices(
        "anthropic", "claude-haiku-4-5", at=datetime(2030, 1, 1, tzinfo=UTC)
    )

    assert (early.input_, early.cached_input, early.output) == (1.0, 0.1, 5.0)
    assert late == early


async def test_the_route_answers_the_live_price_not_the_catalog_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The response carries the snapshot's dollars per million tokens."""
    _serve(
        monkeypatch,
        ModelEntry.entry(
            id=HAIKU,
            name="Claude Haiku 4.5",
            rank="small",
            context_size=200_000,
            input_price=3.0,
            cached_input_price=0.3,
            output_price=15.0,
        ),
    )

    (entry,) = await _models()

    assert (entry["provider"], entry["modelName"]) == ("anthropic", "claude-haiku-4-5")
    assert (entry["inputPrice"], entry["cachedInputPrice"], entry["outputPrice"]) == (
        1.0,
        0.1,
        5.0,
    )


async def test_a_model_the_snapshot_does_not_price_keeps_the_catalog_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(
        monkeypatch,
        ModelEntry.entry(
            id="openai:unpriced",
            name="Unpriced",
            rank="small",
            input_price=0.4,
            cached_input_price=0.04,
            output_price=1.6,
        ),
    )

    (entry,) = await _models()

    assert (entry["inputPrice"], entry["cachedInputPrice"], entry["outputPrice"]) == (
        0.4,
        0.04,
        1.6,
    )
