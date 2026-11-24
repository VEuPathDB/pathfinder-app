from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter
from veupathdb.domain.parameters import ParameterCanonicalizer, ParamValue
from veupathdb.domain.strategy import StepKind, StrategyAst, StrategyStep, walk
from veupathdb.wdk import StrategyAPI, WDKSearch, WDKStrategyDetails
from veupathdb_mcp.catalog import adapt_param_specs_from_search
from veupathdb_mcp.wdk import WireStep

from strategist.ai.lead.verify_checks import _bound_values, _judged
from strategist.domain.site_checks import SiteCheck
from strategist.domain.strategy.session import StrategyGraph
from strategist.services.strategies import held_values, site_changes
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.recorded_searches import suite_search
from strategist.tests.fixtures.builders import add_step_to_graph

D3 = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "turns"
        / "d3_bound_values.json"
    ).read_text()
)
STEP = "step_profile"
SEARCH = suite_search("search_genes_by_ortholog_pattern")
_PARAMS: TypeAdapter[dict[str, ParamValue]] = TypeAdapter(dict[str, ParamValue])


def bound() -> dict[str, ParamValue]:
    return _PARAMS.validate_python(D3["boundParameters"])


def site_step(**wire: str) -> dict[str, Any]:
    step: dict[str, Any] = json.loads(json.dumps(D3["siteStep"]))
    step["searchConfig"]["parameters"].update(wire)
    return step


async def read_the_search(
    site_id: str, record_type: str, search_name: str
) -> WDKSearch:
    del site_id, record_type, search_name
    return SEARCH


async def decode(
    payload: StrategyAst, api: StrategyAPI, wire: dict[str, WireStep]
) -> None:
    del api
    held = ParameterCanonicalizer(adapt_param_specs_from_search(SEARCH))
    for node in walk(payload.root):
        node.parameters = held.held(wire[node.id].parameters)


def the_recorded_site(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(held_values, "catalog_search_definition", read_the_search)
    monkeypatch.setattr(site_changes, "canonicalize_synced_parameters", decode)
    monkeypatch.setattr(site_changes, "get_strategy_api", lambda _site: _NoClient())


class _NoClient:
    client = None


def graph(parameters: Mapping[str, ParamValue] | None = None) -> StrategyGraph:
    built = StrategyGraph("g1", "Orthology Phylogenetic Profile", "plasmodb")
    built.record_type = "transcript"
    add_step_to_graph(
        built,
        StrategyStep(
            id=STEP,
            kind=StepKind.SEARCH,
            search_name=D3["siteStep"]["searchName"],
            parameters=dict(bound() if parameters is None else parameters),
            record_class="transcript",
            display_name="Orthology Phylogenetic Profile",
        ),
    )
    return built


def strategy(step: Mapping[str, Any]) -> WDKStrategyDetails:
    wdk_id = D3["siteStep"]["id"]
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": D3["siteStep"]["strategyId"],
            "name": "Orthology Phylogenetic Profile",
            "rootStepId": wdk_id,
            "recordClassName": "transcript",
            "stepTree": {"stepId": wdk_id},
            "steps": {str(wdk_id): step},
        }
    )


def sync_state() -> WDKSyncState:
    return WDKSyncState(
        wdk_strategy_id=D3["siteStep"]["strategyId"],
        wdk_step_ids={STEP: D3["siteStep"]["id"]},
    )


async def bound_values(
    step: Mapping[str, Any], parameters: Mapping[str, ParamValue] | None = None
) -> SiteCheck:
    judged = _judged("plasmodb", graph(parameters), sync_state(), strategy(step))
    return await _bound_values(judged)
