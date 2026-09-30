"""The site reads every hermetic chat turn needs, served from the recordings."""

from __future__ import annotations

import pytest

from pathfinder.ai.lead import classification_gate
from pathfinder.tests._support.recorded_searches import (
    serve_recorded_listing,
    serve_recorded_record_types,
)
from pathfinder.tests._support.site_organisms import recorded_organisms


@pytest.fixture(autouse=True)
def recorded_site_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """A turn's gate reads the site's organisms and record types; the site is refused."""
    serve_recorded_record_types(monkeypatch)
    serve_recorded_listing(monkeypatch)

    async def _organisms(site_id: str) -> list[str]:
        return recorded_organisms(site_id)

    monkeypatch.setattr(classification_gate, "list_organisms", _organisms)
