"""The models route overlays the live price snapshot on the catalog entry.

``claude-sonnet-5`` is the pinned pair: its snapshot price carries no dated
constraint, so the route's undated lookup answers the same number at any
instant.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from assistant_core.pricing import lookup_per_mtok_prices
from fastapi import FastAPI

from pathfinder.ai.models.catalog import get_model_entry
from pathfinder.transport.http.routers.models import router

SONNET = "anthropic:claude-sonnet-5"


async def _models() -> list[dict[str, Any]]:
    app = FastAPI()
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/models")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    models: list[dict[str, Any]] = body["models"]
    return models


def test_the_pinned_pair_prices_the_same_at_any_instant() -> None:
    """The pinned model's snapshot price holds with no dated constraint."""
    early = lookup_per_mtok_prices(
        "anthropic",
        "claude-sonnet-5",
        at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    late = lookup_per_mtok_prices(
        "anthropic",
        "claude-sonnet-5",
        at=datetime(2030, 1, 1, tzinfo=UTC),
    )

    assert early.input_ == 2.0
    assert early.cached_input == 0.2
    assert early.output == 10.0
    assert late == early


async def test_the_route_answers_the_live_price_not_the_catalog_one() -> None:
    """The response carries the snapshot's dollars per million tokens."""
    catalog = get_model_entry(SONNET)
    assert catalog is not None
    assert catalog.input_price == 3.0
    assert catalog.cached_input_price == 0.3
    assert catalog.output_price == 15.0

    entry = next(model for model in await _models() if model["id"] == SONNET)

    assert entry["provider"] == "anthropic"
    assert entry["modelName"] == "claude-sonnet-5"
    assert entry["name"] == "Claude Sonnet 5"
    assert entry["contextSize"] == 1_000_000
    assert entry["inputPrice"] == 2.0
    assert entry["cachedInputPrice"] == 0.2
    assert entry["outputPrice"] == 10.0
