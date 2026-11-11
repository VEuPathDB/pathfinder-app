"""The site reads every hermetic chat turn needs, served from the recordings."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import FastAPI

from pathfinder.ai.lead import held_intent
from pathfinder.tests._support.recorded_searches import (
    serve_recorded_listing,
    serve_recorded_record_types,
)
from pathfinder.tests._support.site_organisms import recorded_organisms
from pathfinder.tests.integration.http.conftest import client_for


@pytest.fixture(autouse=True)
def recorded_site_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """A turn's gate reads the site's organisms and record types; the site is refused."""
    serve_recorded_record_types(monkeypatch)
    serve_recorded_listing(monkeypatch)

    async def _organisms(site_id: str) -> list[str]:
        return recorded_organisms(site_id)

    monkeypatch.setattr(held_intent, "list_organisms", _organisms)


@pytest.fixture
async def memory_turned_on(app: FastAPI, authed_user_id: UUID) -> None:
    async with client_for(app, authed_user_id) as client:
        response = await client.put("/api/v1/me/memory", json={"enabled": True})
    assert response.json() == {"enabled": True}
