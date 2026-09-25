"""Search definitions and the transcript listing plasmodb published, as recorded.

The client library ships some recordings as package data; the ones only this
suite reads live under ``tests/fixtures/wdk``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import cache
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict
from veupathdb.domain import SearchContext
from veupathdb.domain.strategy import StepValidation
from veupathdb.testing.wdk_fixtures import RecordedWDKResponse, load_recorded
from veupathdb.wdk import WDKSearch, WDKSearchResponse

from pathfinder.ai.tools.standalone import (
    _catalog_models,
    _frame_qualifiers,
    frame_spec,
)

_SUITE = Path(__file__).resolve().parents[1] / "fixtures" / "wdk"


class _Listing(BaseModel):
    """The recorded listing: every search of the record type and its parameter names."""

    model_config = ConfigDict(extra="ignore")

    searches: list[WDKSearch]


def _suite(fixture: str) -> RecordedWDKResponse:
    return RecordedWDKResponse.model_validate_json(
        (_SUITE / f"{fixture}.json").read_text()
    )


def client_search(fixture: str) -> WDKSearch:
    """A definition the client library recorded."""
    body = load_recorded(fixture).json_body()
    return WDKSearchResponse.model_validate(body).search_data


def suite_search(fixture: str) -> WDKSearch:
    """A definition this suite recorded."""
    return WDKSearchResponse.model_validate(_suite(fixture).json_body()).search_data


@cache
def _listing() -> tuple[WDKSearch, ...]:
    body = _suite("transcript_search_param_names").json_body()
    return tuple(_Listing.model_validate(body).searches)


def transcript_listing() -> list[WDKSearch]:
    """Every plasmodb transcript search with the names of its parameters."""
    return list(_listing())


def _response(definition: WDKSearch) -> WDKSearchResponse:
    return WDKSearchResponse(
        search_data=definition,
        validation=StepValidation(level="NONE", is_valid=False),
    )


def serve_qualifier_reads(
    monkeypatch: pytest.MonkeyPatch, read: Callable[[str], WDKSearch]
) -> None:
    """Answer the qualifier rule's reads: plasmodb's transcript listing, and
    each search it compares, by name."""

    async def _catalog(
        ctx: SearchContext, **_kw: object
    ) -> tuple[WDKSearchResponse, str]:
        return _response(read(ctx.search_name)), ctx.record_type

    async def _site_listing(_site: str, _record_type: str) -> list[WDKSearch]:
        return transcript_listing()

    monkeypatch.setattr(_frame_qualifiers, "fetch_search_details", _catalog)
    monkeypatch.setattr(_frame_qualifiers, "get_raw_searches", _site_listing)


def serve_recorded(
    monkeypatch: pytest.MonkeyPatch, definitions: Sequence[WDKSearch]
) -> None:
    """Answer every definition read of set_criterion from these recordings,
    and the record type's listing from plasmodb's."""
    by_name = {d.url_segment: d for d in definitions}

    async def _definition(_site: str, _record_type: str, search_name: str) -> WDKSearch:
        return by_name[search_name]

    async def _catalog(
        ctx: SearchContext, **_kw: object
    ) -> tuple[WDKSearchResponse, str]:
        return _response(by_name[ctx.search_name]), ctx.record_type

    monkeypatch.setattr(frame_spec, "read_search_definition", _definition)
    monkeypatch.setattr(_catalog_models, "read_search_definition", _definition)
    monkeypatch.setattr(frame_spec, "fetch_search_details", _catalog)
    serve_qualifier_reads(monkeypatch, by_name.__getitem__)
