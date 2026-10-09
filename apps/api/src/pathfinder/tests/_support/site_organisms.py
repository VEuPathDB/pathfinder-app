"""The organism vocabulary each site declared, as ``list_organisms`` recorded it."""

from __future__ import annotations

from pathlib import Path

import pytest
from veupathdb.model import CamelModel

from pathfinder.ai.lead import classification_gate
from pathfinder.tests._support.qa_recording import qa_recording

_RECORDED = Path(__file__).resolve().parents[1] / "fixtures" / "organisms"


class RecordedOrganisms(CamelModel):
    site: str
    recorded_on: str
    source: str
    organisms: list[str]


def recorded_organisms(site_id: str) -> list[str]:
    """Every organism the site declared on the day of the recording."""
    path = qa_recording(_RECORDED / f"{site_id}.json")
    return RecordedOrganisms.model_validate_json(path.read_text()).organisms


def serve_recorded_organisms(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Serve the classification gate each site's recording; each read is recorded."""
    reads: list[str] = []

    async def _organisms(site_id: str) -> list[str]:
        reads.append(site_id)
        return recorded_organisms(site_id)

    monkeypatch.setattr(classification_gate, "list_organisms", _organisms)
    return reads
