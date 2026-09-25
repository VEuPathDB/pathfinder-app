"""Search definitions and the transcript listing plasmodb published, as recorded.

The client library ships some recordings as package data; the ones only this
suite reads live under ``tests/fixtures/wdk``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from functools import cache
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import StepValidation
from veupathdb.errors import WDKError
from veupathdb.testing.wdk_fixtures import RecordedWDKResponse, load_recorded
from veupathdb.wdk import VEuPathDBClient, WDKSearch, WDKSearchResponse
from veupathdb_mcp import tool_payloads
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParamFetcher,
    ResolvedSearch,
    ValidationCallbacks,
    format_param_info_typed,
)
from veupathdb_mcp.tool_payloads import SearchListing

from pathfinder.ai.tools.standalone import (
    _catalog_models,
    _frame_count,
    _frame_qualifiers,
    frame_spec,
)
from pathfinder.services.strategies import (
    sheet_params,
    spec_build,
    stated_sides,
    step_wdk_push,
    sync,
)
from pathfinder.tests._support.catalog_builders import serve_search_details

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


@cache
def _listed_names() -> frozenset[str]:
    return frozenset(s.url_segment for s in _listing())


async def _listed_under(search_name: str | None) -> str | None:
    """The record type plasmodb lists the search under, as the catalog finds it."""
    return "transcript" if search_name in _listed_names() else None


def _recorded_validation_callbacks() -> ValidationCallbacks:
    """Callbacks that find a search's record type in plasmodb's recorded
    transcript listing."""

    async def _resolve(_record_type: str | None, search_name: str | None) -> str | None:
        return await _listed_under(search_name)

    async def _hint(_search_name: str, _record_type: str | None) -> str | None:
        return None

    return ValidationCallbacks(
        resolve_record_type_for_search=_resolve, find_record_type_hint=_hint
    )


def serve_recorded_record_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """Find each search's record type in plasmodb's recorded listing, wherever
    a binding, a write or a push asks the catalog."""
    for module in (frame_spec, stated_sides, step_wdk_push, spec_build):
        monkeypatch.setattr(
            module,
            "make_validation_callbacks",
            lambda _site_id: _recorded_validation_callbacks(),
        )

    async def _resolver(_site_id: str) -> Callable[[str], Awaitable[str | None]]:
        return _listed_under

    async def _owner(_site_id: str, search_name: str, record_type: str | None) -> str:
        return record_type or await _listed_under(search_name) or "transcript"

    monkeypatch.setattr(sync, "make_record_type_resolver", _resolver)
    for module in (frame_spec, sheet_params):
        monkeypatch.setattr(module, "resolve_search_record_type", _owner)


def serve_recorded_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer ``list_search_listings`` with plasmodb's recorded transcript listing."""

    async def _listings(_site_id: str, _record_type: str) -> list[SearchListing]:
        return [
            SearchListing(name=s.url_segment, display_name=s.display_name)
            for s in _listing()
        ]

    monkeypatch.setattr(tool_payloads, "list_search_listings", _listings)


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


def no_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """A served search publishes no count, so a binding reads none."""

    async def _count(*_args: object, **_kwargs: object) -> int | None:
        return None

    monkeypatch.setattr(_frame_count, "count_bound_criterion", _count)


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


def serve_recorded_definitions(
    monkeypatch: pytest.MonkeyPatch, definitions: Sequence[WDKSearch]
) -> None:
    """Answer every read of a search definition from these recordings, by name:
    the catalog's in ``validate_parameters`` and the WDK client's own.

    A recording holds no caller values, so the catalog reads it as the
    published definition and casts no verdict from it. A search with no
    recording is one the site does not publish.
    """
    by_name = {d.url_segment: d for d in definitions}

    def _recorded(search_name: str) -> WDKSearchResponse:
        if search_name not in by_name:
            msg = f"no recording of {search_name}"
            raise WDKError(msg, 404)
        return _response(by_name[search_name])

    async def _resolve(
        ctx: SearchContext,
        /,
        *,
        resolved_record_type: str,
        parameters: dict[str, ParamValue],
    ) -> ResolvedSearch:
        del resolved_record_type, parameters
        return ResolvedSearch(
            response=_recorded(ctx.search_name), values_were_read=False
        )

    async def _client_read(
        _client: VEuPathDBClient,
        _record_type: str,
        search_name: str,
        *,
        expand_params: bool = True,
    ) -> WDKSearchResponse:
        del expand_params
        return _recorded(search_name)

    serve_search_details(monkeypatch, _resolve)
    monkeypatch.setattr(VEuPathDBClient, "get_search_details", _client_read)


def serve_recorded_plasmodb(
    monkeypatch: pytest.MonkeyPatch, definitions: Sequence[WDKSearch]
) -> None:
    """A whole turn on plasmodb reads the recorded listing and these recorded
    definitions, and the site publishes no count."""
    serve_recorded_listing(monkeypatch)
    serve_recorded(monkeypatch, definitions)
    serve_recorded_definitions(monkeypatch, definitions)
    serve_recorded_record_types(monkeypatch)
    no_count(monkeypatch)
    by_name = {d.url_segment: d for d in definitions}

    def _fetch_at(_site_id: str, _record_type: str, search_name: str) -> ParamFetcher:
        async def fetch_at(_context: dict[str, str]) -> list[ParameterInfo]:
            return format_param_info_typed(by_name[search_name].parameters or [])

        return fetch_at

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)
