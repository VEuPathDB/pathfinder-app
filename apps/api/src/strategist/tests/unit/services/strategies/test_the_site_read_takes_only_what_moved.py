"""The site read takes a value or a setting only when it states something new.

A wire value is compared in both forms the step holds: spelled another way
and decoding to the stored value, it has not moved.
"""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import NumberValue, ParamValue
from veupathdb.domain.strategy import (
    ColocationParams,
    CombineOp,
    StepFilter,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
    walk,
)
from veupathdb.wdk import StrategyAPI, WDKStrategyDetails
from veupathdb_mcp.wdk import WireStep

from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.unread import Unread
from strategist.services.strategies import site_changes
from strategist.services.strategies.site_changes import (
    SiteEdits,
    take_what_the_site_holds,
)
from strategist.services.strategies.sync_state import WDKSyncState

_LEAF = "step_exportpred"
_WDK_ID = 440537303
_SCORE = "min_exportpred_score"


async def _decode(
    payload: StrategyAst, api: StrategyAPI, wire: dict[str, WireStep]
) -> None:
    """Decode every wire value as a number, the way a number parameter decodes."""
    del api
    for node in walk(payload.root):
        if node.id not in wire:
            continue
        node.parameters = {
            name: NumberValue(value=float(value))
            for name, value in wire[node.id].parameters.items()
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
                    "recordClassName": "transcript",
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

    async def test_a_weight_set_on_a_step_with_none_is_taken(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = _graph(None)

        edits = await _read(monkeypatch, graph, _site("10", wdkWeight=5))

        assert (edits.valued, graph.steps[_LEAF].wdk_weight) == ([_LEAF], 5)

    async def test_a_weight_cleared_on_the_site_is_taken(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = _graph(3)

        edits = await _read(monkeypatch, graph, _site("10", wdkWeight=0))

        assert (edits.valued, graph.steps[_LEAF].wdk_weight) == ([_LEAF], None)


_DEFAULT = StepFilter(name="matched_transcript_filter_array", value={"values": ["Y"]})
_SET = StepFilter(name="gene_boolean_filter_array", value={"values": ["YN"]})


class TestAFilter:
    async def test_a_filter_wdk_added_is_not_taken(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = _graph(None)
        graph.steps[_LEAF].filters_wdk_added = [_DEFAULT]

        edits = await _read(
            monkeypatch, graph, _site("10", filters=[_DEFAULT.model_dump()])
        )

        assert (edits.valued, graph.steps[_LEAF].filters) == ([], [])

    async def test_a_filter_set_on_the_site_is_taken(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = _graph(None)
        graph.steps[_LEAF].filters_wdk_added = [_DEFAULT]

        edits = await _read(
            monkeypatch,
            graph,
            _site("10", filters=[_DEFAULT.model_dump(), _SET.model_dump()]),
        )

        assert (edits.valued, graph.steps[_LEAF].filters) == ([_LEAF], [_SET])


_SPAN = 440537310
_FEATURES = 440537304


def _colocated_graph() -> StrategyGraph:
    graph = StrategyGraph("g1", "colocated", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_span",
            search_name="__combine__",
            operator=CombineOp.COLOCATE,
            colocation_params=ColocationParams(),
            primary_input=StrategyStepNode(
                id=_LEAF,
                search_name="GenesByExportPred",
                parameters={_SCORE: NumberValue(value=10)},
            ),
            secondary_input=StrategyStepNode(
                id="step_features", search_name="GenesByExportPred"
            ),
        )
    )
    graph.recompute_roots()
    return graph


def _colocated_site(params: ColocationParams, **span: Any) -> WDKStrategyDetails:
    leaf = {
        "searchName": "GenesByExportPred",
        "searchConfig": {"parameters": {_SCORE: "10"}},
        "recordClassName": "transcript",
        "strategyId": 330679883,
    }
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": 330679883,
            "name": "colocated",
            "rootStepId": _SPAN,
            "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
            "stepTree": {
                "stepId": _SPAN,
                "primaryInput": {"stepId": _WDK_ID},
                "secondaryInput": {"stepId": _FEATURES},
            },
            "steps": {
                str(_WDK_ID): {"id": _WDK_ID, **leaf},
                str(_FEATURES): {"id": _FEATURES, **leaf},
                str(_SPAN): {
                    "id": _SPAN,
                    "searchName": "GenesBySpanLogic",
                    "searchConfig": {"parameters": params.to_wdk_params()},
                    "recordClassName": "transcript",
                    "strategyId": 330679883,
                    **span,
                },
            },
        }
    )


async def _read_colocated(
    monkeypatch: pytest.MonkeyPatch, graph: StrategyGraph, live: WDKStrategyDetails
) -> SiteEdits:
    monkeypatch.setattr(site_changes, "canonicalize_synced_parameters", _decode)
    monkeypatch.setattr(site_changes, "get_strategy_api", lambda _site: None)
    return await take_what_the_site_holds(
        graph=graph,
        sync_state=WDKSyncState(
            wdk_step_ids={
                _LEAF: _WDK_ID,
                "step_features": _FEATURES,
                "step_span": _SPAN,
            },
            wdk_strategy_id=330679883,
        ),
        site_id="plasmodb",
        live=live,
    )


async def test_a_colocation_moved_on_the_site_is_taken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _colocated_graph()
    moved = ColocationParams(begin_offset_a=200)

    edits = await _read_colocated(monkeypatch, graph, _colocated_site(moved))

    assert (edits.valued, graph.steps["step_span"].colocation_params) == (
        ["step_span"],
        moved,
    )


def _grouped(saved: int | None) -> StrategyGraph:
    graph = _colocated_graph()
    span = graph.steps["step_span"]
    span.expanded_name = "Near exported"
    span.expanded_strategy_id = saved
    return graph


@pytest.mark.parametrize("saved", [None, 777])
async def test_a_group_the_site_left_alone_keeps_what_it_expands(
    monkeypatch: pytest.MonkeyPatch, saved: int | None
) -> None:
    graph = _grouped(saved)
    live = _colocated_site(
        ColocationParams(), expanded=True, expandedName="Near exported"
    )

    edits = await _read_colocated(monkeypatch, graph, live)

    assert (edits.valued, graph.steps["step_span"].expanded_strategy_id) == (
        [],
        saved,
    )


async def test_a_group_renamed_on_the_site_is_taken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _grouped(777)
    live = _colocated_site(ColocationParams(), expanded=True, expandedName="Renamed")

    edits = await _read_colocated(monkeypatch, graph, live)

    span = graph.steps["step_span"]
    assert (edits.valued, span.expanded_name, span.expanded_strategy_id) == (
        ["step_span"],
        "Renamed",
        777,
    )


async def test_an_unreadable_site_tree_gives_nothing_not_even_a_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _colocated_graph()
    live = _colocated_site(ColocationParams())
    live.steps[str(_WDK_ID)].search_config.parameters[_SCORE] = "12"
    live.steps[str(_SPAN)].search_config.parameters.clear()

    edits = await _read_colocated(monkeypatch, graph, live)

    assert (edits.moved, graph.steps[_LEAF].parameters[_SCORE]) == (
        False,
        NumberValue(value=10),
    )
    assert edits.not_read == Unread(
        reason="the site's tree was not read: Data parsing failed: span logic "
        "step has no span_operation, span_strand, span_output, region_a, "
        "span_begin_a, span_begin_direction_a, span_begin_offset_a, span_end_a, "
        "span_end_direction_a, span_end_offset_a, region_b, span_begin_b, "
        "span_begin_direction_b, span_begin_offset_b, span_end_b, "
        "span_end_direction_b, span_end_offset_b"
    )
