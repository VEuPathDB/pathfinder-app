"""The WDK and catalog wire one organism-swap turn runs over."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from veupathdb.domain.parameters.wdk_vocab import VocabOption
from veupathdb.domain.search import SearchContext
from veupathdb.domain.strategy.validation import StepValidation
from veupathdb.wdk.wdk_models import (
    WDKSearch,
    WDKSearchConfig,
    WDKSearchResponse,
    WDKStep,
    WDKStepTree,
    WDKStrategyDetails,
)
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParamFetcher,
    ValidatedParams,
    param_discovery,
    searches,
)

from pathfinder.ai.lead import edit_dispatch
from pathfinder.ai.tools.standalone import frame_spec
from pathfinder.services.strategies import commit, live_counts, step_wdk_push, sync

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


@dataclass
class Call:
    name: str
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecordingAPI:
    calls: list[Call] = field(default_factory=list)

    def named(self, name: str) -> list[Call]:
        return [c for c in self.calls if c.name == name]

    async def delete_step(self, step_id: int, *, user_id: str | None = None) -> None:
        del user_id
        self.calls.append(Call("delete_step", {"step_id": step_id}))

    async def update_step_search_config(
        self,
        step_id: int,
        search_config: WDKSearchConfig,
        record_type: str,
        search_name: str,
        *,
        user_id: str | None = None,
    ) -> None:
        del user_id, record_type
        self.calls.append(
            Call(
                "update_step_search_config",
                {
                    "step_id": step_id,
                    "search_name": search_name,
                    "parameters": dict(search_config.parameters),
                },
            )
        )

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByProfile",
            search_config=WDKSearchConfig(parameters={}),
        )

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del user_id
        return WDKStrategyDetails(
            strategy_id=strategy_id,
            name="Test strategy",
            root_step_id=500,
            step_tree=WDKStepTree(step_id=500),
            steps={
                str(wdk_id): WDKStep(
                    id=wdk_id,
                    search_name="GenesByProfile",
                    search_config=WDKSearchConfig(parameters={}),
                    estimated_size=11,
                )
                for wdk_id in WDK_IDS.values()
            },
        )


def _organism_info() -> ParameterInfo:
    return ParameterInfo(
        name="organism",
        display_name="organism",
        type="multi-pick-vocabulary",
        required=True,
        is_visible=True,
        help="",
        value_format="",
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
        help="",
        value_format="",
        default_value=default,
        allowed_values=options,
        vocab_depends_on=["organism"],
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
    for module in (commit, step_wdk_push, sync, live_counts):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)

    async def _noop_validate_plan(*_a: Any, **_k: Any) -> set[str]:
        return set()

    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", _noop_validate_plan)

    async def _noop_reconcile(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(commit, "reconcile_sync_state_with_wdk", _noop_reconcile)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _chunk: None)

    def _fetch_at(*_args: object) -> ParamFetcher:
        async def fetch_at(context: dict[str, str]) -> list[ParameterInfo]:
            return _params_under(context)

        return fetch_at

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)

    client = _SearchDetailsClient()
    monkeypatch.setattr(searches, "get_wdk_client", lambda _site: client)

    async def _details(
        ctx: SearchContext, **_kw: object
    ) -> tuple[WDKSearchResponse, str]:
        return (_search_response(ctx.search_name), "etag")

    monkeypatch.setattr(param_discovery, "fetch_search_details", _details)
    monkeypatch.setattr(frame_spec, "fetch_search_details", _details)

    async def _validate(*_a: object, **_k: object) -> ValidatedParams:
        return ValidatedParams()

    monkeypatch.setattr(frame_spec, "validate_parameters", _validate)
    return api
