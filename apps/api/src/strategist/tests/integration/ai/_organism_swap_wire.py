"""The WDK and catalog wire one organism-swap turn runs over."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

import pytest
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue, VocabOption
from veupathdb.domain.strategy import StepValidation
from veupathdb.wdk import (
    WDKParameter,
    WDKSearch,
    WDKSearchResponse,
)
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParamFetcher,
    ValidatedParams,
    param_discovery,
    searches,
)

from strategist.ai.lead import edit_dispatch
from strategist.ai.tools.standalone import _frame_canonical, frame_spec
from strategist.services.strategies import (
    commit_tree,
    live_counts,
    record_classes,
    sheet_params,
)
from strategist.tests._support import wdk_write_stubs
from strategist.tests._support.recorded_searches import (
    no_count,
)
from strategist.tests._support.recording_wdk import RecordingWDK, served
from strategist.tests._support.sheets import declarations

PF = "Plasmodium falciparum 3D7"
PV = "Plasmodium vivax P01"
DERISI = "DeRisi 3D7 Smoothed"
ZHU = "Zhu P01 time course"

WDK_IDS = {
    "step_text": 100,
    "step_go": 200,
    "step_c1": 300,
    "step_expr": 400,
    "step_c2": 500,
}


class RecordingAPI(RecordingWDK):
    def __init__(self) -> None:
        super().__init__()
        self.wdk.answer_size = 11


def _organism_info() -> ParameterInfo:
    return ParameterInfo(
        name="organism",
        display_name="organism",
        type="multi-pick-vocabulary",
        required=True,
        is_visible=True,
        site_set=False,
        help="",
        organism_param=True,
        stated_children=["profileset"],
        wire_children=["profileset"],
        vocab_leaves=[
            VocabOption(value=PF, display="P. falciparum 3D7"),
            VocabOption(value=PV, display="P. vivax P01"),
        ],
    )


def _profileset_info(options: list[VocabOption], default: str) -> ParameterInfo:
    return ParameterInfo(
        name="profileset",
        display_name="profileset",
        type="single-pick-vocabulary",
        required=True,
        is_visible=True,
        site_set=False,
        help="",
        default_value=default,
        allowed_values=options,
        stated_parents=["organism"],
        wire_parents=["organism"],
    )


def _params_under(context: dict[str, str]) -> list[ParameterInfo]:
    if PV in context.get("organism", ""):
        return [
            _organism_info(),
            _profileset_info([VocabOption(value=ZHU, display="Zhu P01")], ZHU),
        ]
    return [
        _organism_info(),
        _profileset_info([VocabOption(value=DERISI, display=DERISI)], DERISI),
    ]


def _search_response(search_name: str) -> WDKSearchResponse:
    """A search the catalog serves, with no validation of its own."""
    return WDKSearchResponse(
        search_data=WDKSearch(url_segment=search_name),
        validation=StepValidation(level="NONE", is_valid=False),
    )


class _SearchDetailsClient:
    """The one WDK call the catalog makes while this turn resolves parameters."""

    async def get_search_details(
        self, record_type: str, name: str, *, expand_params: bool = True
    ) -> WDKSearchResponse:
        del record_type, expand_params
        return _search_response(name)


@pytest.fixture
def wdk(monkeypatch: pytest.MonkeyPatch) -> RecordingAPI:
    api = RecordingAPI()
    monkeypatch.setitem(served, "site", api)
    for module in (commit_tree, live_counts):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)

    wdk_write_stubs.stub_every_catalog_read(monkeypatch)
    no_count(monkeypatch)

    async def _transcript(_search_name: str) -> str:
        return "transcript"

    async def _resolver(_site_id: str) -> Callable[[str], Awaitable[str | None]]:
        return _transcript

    monkeypatch.setattr(record_classes, "make_record_type_resolver", _resolver)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _chunk: None)

    def _fetch_at(*_args: object) -> ParamFetcher:
        async def fetch_at(context: dict[str, str]) -> list[WDKParameter]:
            return declarations(_params_under(context))

        return fetch_at

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)

    client = _SearchDetailsClient()
    monkeypatch.setattr(searches, "get_wdk_client", lambda _site: client)

    async def _details(
        ctx: SearchContext, **_kw: object
    ) -> tuple[WDKSearchResponse, str]:
        return (_search_response(ctx.search_name), "etag")

    monkeypatch.setattr(param_discovery, "fetch_search_details", _details)
    monkeypatch.setattr(sheet_params, "fetch_search_details", _details)

    async def _validate(
        _search: object,
        *,
        stated: Mapping[str, ParamValue],
        callbacks: object,
        **_held: object,
    ) -> ValidatedParams:
        del callbacks
        return ValidatedParams(params=dict(stated))

    monkeypatch.setattr(_frame_canonical, "validate_parameters", _validate)
    return api
