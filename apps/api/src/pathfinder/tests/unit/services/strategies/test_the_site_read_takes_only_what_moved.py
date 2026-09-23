"""The site read takes a value or a weight only when it states something new.

A wire value is compared in both forms the step holds: spelled another way
and decoding to the stored value, it has not moved.
"""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import NumberValue, ParamValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree, walk
from veupathdb.wdk import StrategyAPI, WDKStrategyDetails

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import site_changes
from pathfinder.services.strategies.site_changes import (
    SiteEdits,
    take_what_the_site_holds,
)
from pathfinder.services.strategies.sync_state import WDKSyncState

_LEAF = "step_exportpred"
_WDK_ID = 440537303
_SCORE = "min_exportpred_score"


async def _decode(
    payload: StrategyAst, api: StrategyAPI, wire: dict[str, dict[str, str]]
) -> None:
    """Decode every wire value as a number, the way a number parameter decodes."""
    del api
    for node in walk(payload.root):
        node.parameters = {
            name: NumberValue(value=float(value))
            for name, value in wire.get(node.id, {}).items()
        }


def _graph(weight: int | None) -> StrategyGraph:
    params: dict[str, ParamValue] = {_SCORE: NumberValue(value=10)}
    graph = StrategyGraph("g1", "exported", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id=_LEAF,
            search_name="GenesByExportPred",
            parameters=params,
            wdk_weight=weight,
        )
    )
    graph.recompute_roots()
    return graph


def _site(score: str, **config: Any) -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": 330679883,
            "name": "exported",
            "rootStepId": _WDK_ID,
            "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
            "stepTree": {"stepId": _WDK_ID},
            "steps": {
                str(_WDK_ID): {
                    "id": _WDK_ID,
                    "searchName": "GenesByExportPred",
                    "searchConfig": {"parameters": {_SCORE: score}, **config},
                }
            },
        }
    )


async def _read(
    monkeypatch: pytest.MonkeyPatch, graph: StrategyGraph, live: WDKStrategyDetails
) -> SiteEdits:
    monkeypatch.setattr(site_changes, "canonicalize_synced_parameters", _decode)
    monkeypatch.setattr(site_changes, "get_strategy_api", lambda _site: None)
    return await take_what_the_site_holds(
        graph=graph,
        sync_state=WDKSyncState(
            wdk_step_ids={_LEAF: _WDK_ID}, wdk_strategy_id=330679883
        ),
        site_id="plasmodb",
        live=live,
    )


class TestAValue:
    async def test_a_value_spelled_another_way_is_not_taken(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = _graph(None)

        edits = await _read(monkeypatch, graph, _site("10.0"))

        assert edits.valued == []

    async def test_a_value_that_decodes_to_another_value_is_taken(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = _graph(None)

        edits = await _read(monkeypatch, graph, _site("12.0"))

        assert (edits.valued, graph.steps[_LEAF].parameters[_SCORE]) == (
            [_LEAF],
            NumberValue(value=12),
        )


class TestAWeight:
    async def test_a_weight_set_on_the_site_is_taken(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = _graph(3)

        edits = await _read(monkeypatch, graph, _site("10", wdkWeight=5))

        assert (edits.valued, graph.steps[_LEAF].wdk_weight) == ([_LEAF], 5)

    async def test_a_graph_with_no_weight_keeps_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = _graph(None)

        edits = await _read(monkeypatch, graph, _site("10", wdkWeight=5))

        assert (edits.valued, graph.steps[_LEAF].wdk_weight) == ([], None)

    async def test_a_site_that_states_no_weight_moves_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = _graph(3)

        edits = await _read(monkeypatch, graph, _site("10"))

        assert (edits.valued, graph.steps[_LEAF].wdk_weight) == ([], 3)
