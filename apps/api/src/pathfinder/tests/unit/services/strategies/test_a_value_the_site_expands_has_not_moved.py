"""A tree value the site stores as its leaves is the value the step pushed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter
from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree, walk
from veupathdb.wdk import StrategyAPI, WDKParameter, WDKStep, WDKStrategyDetails
from veupathdb.wdk.tree_leaves import leaves_of_tree_values
from veupathdb_mcp.wdk import WireStep

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import site_changes
from pathfinder.services.strategies.sync_state import WDKSyncState

_RECORDED = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "site_values"
        / "genus_organism.json"
    ).read_text()
)
_PARAMETER: WDKParameter = TypeAdapter(WDKParameter).validate_python(
    _RECORDED["parameter"]
)
_STORED = WDKStep.model_validate(_RECORDED["stored"])
_LEAF = "step_go"


class _Client:
    async def expand_tree_params_to_leaves(
        self, record_type: str, search_name: str, params: dict[str, str]
    ) -> dict[str, str]:
        del record_type
        return leaves_of_tree_values([_PARAMETER], params, search_name)


async def _decode(
    payload: StrategyAst, api: StrategyAPI, wire: dict[str, WireStep]
) -> None:
    del api
    for node in walk(payload.root):
        node.parameters = {
            name: MultiPickValue(values=json.loads(value))
            if value.startswith("[")
            else StringValue(value=value)
            for name, value in wire[node.id].parameters.items()
        }


def _step(organism: list[str]) -> StrategyGraph:
    params: dict[str, ParamValue] = {
        "organism": MultiPickValue(values=organism),
        "go_typeahead": MultiPickValue(values=["GO:0020037"]),
        "go_term_evidence": MultiPickValue(values=["Curated", "Computed"]),
        "go_term_slim": StringValue(value="No"),
    }
    graph = StrategyGraph("g1", "heme binding", "veupathdb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(id=_LEAF, search_name="GenesByGoTerm", parameters=params)
    )
    graph.recompute_roots()
    return graph


@pytest.fixture
def the_recorded_site(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(site_changes, "get_wdk_client", lambda _site: _Client())
    monkeypatch.setattr(site_changes, "canonicalize_synced_parameters", _decode)
    monkeypatch.setattr(site_changes, "get_strategy_api", lambda _site: None)


def _live() -> WDKStrategyDetails:
    stored: dict[str, Any] = _STORED.model_dump(by_alias=True, mode="json")
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": 214648110,
            "name": "heme binding",
            "rootStepId": _STORED.id,
            "recordClassName": "transcript",
            "stepTree": {"stepId": _STORED.id},
            "steps": {str(_STORED.id): stored},
        }
    )


@pytest.mark.usefixtures("the_recorded_site")
async def test_the_genus_stored_as_its_strains_holds_no_other_value() -> None:
    graph = _step(["Plasmodium"])

    held = await site_changes.values_the_site_holds_otherwise(
        graph.steps[_LEAF], _STORED, "veupathdb"
    )

    assert held == {}


@pytest.mark.usefixtures("the_recorded_site")
async def test_a_read_of_the_expanded_genus_keeps_the_genus() -> None:
    graph = _step(["Plasmodium"])

    edits = await site_changes.take_what_the_site_holds(
        graph=graph,
        sync_state=WDKSyncState(
            wdk_step_ids={_LEAF: _STORED.id}, wdk_strategy_id=214648110
        ),
        site_id="veupathdb",
        live=_live(),
    )

    assert (edits.valued, graph.steps[_LEAF].parameters["organism"]) == (
        [],
        MultiPickValue(values=["Plasmodium"]),
    )


@pytest.mark.usefixtures("the_recorded_site")
async def test_one_species_is_not_the_genus_the_site_holds() -> None:
    graph = _step(["Plasmodium falciparum"])

    held = await site_changes.values_the_site_holds_otherwise(
        graph.steps[_LEAF], _STORED, "veupathdb"
    )

    assert list(held) == ["organism"]
    assert len(json.loads(held["organism"])) == 61
