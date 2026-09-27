"""The record classes each search declares, served offline from the recorded
search definitions under ``tests/fixtures/wdk``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import cache
from pathlib import Path

import pytest
from veupathdb.testing.wdk_fixtures import RecordedWDKResponse
from veupathdb.wdk import WDKRecordType, WDKSearch, WDKSearchResponse

from pathfinder.services.strategies import record_classes
from pathfinder.tests._support.organism_reads import TRANSCRIPT

_SUITE = Path(__file__).resolve().parents[1] / "fixtures" / "wdk"
# The compound record type as plasmodb publishes it.
COMPOUND = WDKRecordType(
    url_segment="compound",
    display_name="Compound",
    display_name_plural="Compounds",
    short_display_name="Compound",
)


@cache
def recorded_searches() -> dict[str, WDKSearch]:
    """Every search definition this suite recorded, by search name."""
    found: dict[str, WDKSearch] = {}
    for path in sorted(_SUITE.glob("search_*.json")):
        body = RecordedWDKResponse.model_validate_json(path.read_text()).json_body()
        search = WDKSearchResponse.model_validate(body).search_data
        found[search.url_segment] = search
    return found


def serve_record_classes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer each recorded search's record classes; any other search is unlisted."""

    async def _resolver(_site_id: str) -> Callable[[str], Awaitable[str | None]]:
        async def _listed_under(search_name: str) -> str | None:
            search = recorded_searches().get(search_name)
            return None if search is None else search.output_record_class_name

        return _listed_under

    async def _searches(_site_id: str, record_type: str) -> list[WDKSearch]:
        return [
            s
            for s in recorded_searches().values()
            if s.output_record_class_name == record_type
        ]

    async def _record_types(_site_id: str) -> list[WDKRecordType]:
        return [TRANSCRIPT, COMPOUND]

    monkeypatch.setattr(record_classes, "make_record_type_resolver", _resolver)
    monkeypatch.setattr(record_classes, "get_raw_searches", _searches)
    monkeypatch.setattr(record_classes, "get_raw_record_types", _record_types)
