"""A bound text is judged unset against the value the site publishes, never
against a sheet read under the bound values, where WDK answers each sent value
as that parameter's initial value."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from veupathdb.domain.parameters import ParamValue
from veupathdb.wdk import SiteSearchResponse
from veupathdb_mcp.catalog import ParameterInfo, ParamFetcher, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone import _frame_count, frame_spec
from pathfinder.domain.caveats import phrase_caveats
from pathfinder.domain.strategy.operational_spec import Measurement
from pathfinder.tests._support.recorded_counts import (
    serve_counts,
    serve_site_search,
    wire,
)
from pathfinder.tests._support.recorded_searches import serve_recorded, suite_search
from pathfinder.tests.unit.ai.tools._rationale_catalog import SITE
from pathfinder.tests.unit.ai.tools.conftest import serve_no_other_sites
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    bind,
    no_validation,
    serve_site_listing,
)

_PUBLISHED = suite_search("search_giardiadb_genes_by_text")
_UNDER_CONTEXT = suite_search("search_giardiadb_genes_by_text_under_context")
_MESSAGE = (
    "Giardia muris Roberts-Thompson genes with a cysteine-rich protein annotation."
)
_TEXT = "cysteine-rich protein"
# GiardiaDB GenesByText over product, Products and Notes in G. muris, read live:
# the unquoted text 4,497 genes, the quoted phrase 0.
_WORDS, _PHRASE = 4497, 0
_PARAMS: dict[str, str | list[str] | None] = {
    "text_fields": ["product", "Products", "Notes"],
    "document_type": "gene",
    "text_expression": _TEXT,
    "text_search_organism": ["Giardia muris strain Roberts-Thomson"],
}


def _count(_search: str, params: Mapping[str, ParamValue]) -> int:
    return _PHRASE if wire(params, "text_expression").startswith('"') else _WORDS


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded(monkeypatch, [_PUBLISHED])

    def _fetch_at(_site: str, _record_type: str, _search: str) -> ParamFetcher:
        async def fetch_at(context: dict[str, str]) -> list[ParameterInfo]:
            read = _UNDER_CONTEXT if context else _PUBLISHED
            return format_param_info_typed(list(read.parameters or []))

        return fetch_at

    async def _bound_count(*_args: object, **_kwargs: object) -> int:
        return _WORDS

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)
    monkeypatch.setattr(_frame_count, "count_bound_criterion", _bound_count)
    no_validation(monkeypatch)
    serve_site_listing(monkeypatch, SITE)
    serve_no_other_sites(monkeypatch)
    serve_counts(monkeypatch, _count)
    serve_site_search(monkeypatch, SiteSearchResponse())


def test_the_context_read_answers_the_bound_text_as_its_initial_value() -> None:
    published = {
        i.name: i.default_value
        for i in format_param_info_typed(list(_PUBLISHED.parameters or []))
    }
    under = {
        i.name: i.default_value
        for i in format_param_info_typed(list(_UNDER_CONTEXT.parameters or []))
    }

    assert (published["text_expression"], under["text_expression"]) == (
        "*reductase",
        _TEXT,
    )


@pytest.mark.asyncio
async def test_a_text_bound_on_a_search_with_a_dependent_parameter_keeps_its_phrase_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = AgentToolState()
    state.request_messages = [_MESSAGE]

    await bind(state, "GenesByText", dict(_PARAMS), text=_MESSAGE)

    [criterion] = state.operational_spec_draft.criteria
    assert [m for m in criterion.measurements if m.kind == "wildcard_phrase"] == [
        Measurement(
            kind="wildcard_phrase",
            param="text_expression",
            count=_PHRASE,
            reading=f'"{_TEXT}"',
        )
    ]
    [caveat] = phrase_caveats(state.operational_spec_draft)
    assert caveat.sentence == (
        "Text term (use * as wildcard) 'cysteine-rich protein' matches any of its "
        'words: 4,497 genes; as the phrase "cysteine-rich protein": 0 genes'
    )


@pytest.mark.asyncio
async def test_a_pick_is_read_at_the_default_the_site_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = AgentToolState()
    state.request_messages = [_MESSAGE]

    await bind(state, "GenesByText", dict(_PARAMS), text=_MESSAGE)

    [criterion] = state.operational_spec_draft.criteria
    assert [
        (m.kind, m.count, m.reading)
        for m in criterion.measurements
        if m.param == "text_fields" and m.kind != "vocabulary_label"
    ] == [("site_default", _WORDS, "all 27 options")]


@pytest.mark.asyncio
async def test_each_measurement_reaches_frame_as_one_clause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = AgentToolState()
    state.request_messages = [_MESSAGE]

    result = await bind(state, "GenesByText", dict(_PARAMS), text=_MESSAGE)

    assert result.measurements
    assert len(result.measurements) == len(set(result.measurements))
