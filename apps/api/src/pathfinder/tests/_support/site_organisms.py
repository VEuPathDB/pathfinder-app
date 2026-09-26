"""The organism vocabulary each site declared, as ``list_organisms`` recorded it."""

from __future__ import annotations

from pathlib import Path

from veupathdb.model import CamelModel

_RECORDED = Path(__file__).resolve().parents[1] / "fixtures" / "organisms"


class RecordedOrganisms(CamelModel):
    site: str
    recorded_on: str
    source: str
    organisms: list[str]


def recorded_organisms(site_id: str) -> list[str]:
    """Every organism the site declared on the day of the recording."""
    path = _RECORDED / f"{site_id}.json"
    return RecordedOrganisms.model_validate_json(path.read_text()).organisms
