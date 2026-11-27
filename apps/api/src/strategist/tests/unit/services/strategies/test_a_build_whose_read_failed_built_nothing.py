from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import WDKSearchResponse, turn_reads

from strategist.domain.strategy.operations import ReplaceStrategyOp
from strategist.services.strategies.commit import apply_operations_and_commit
from strategist.services.strategies.spec_build import build_strategy_from_spec
from strategist.tests._support.holding_wdk import HoldingWDK
from strategist.tests._support.recorded_searches import (
    serve_recorded_definitions,
    suite_search,
)
from strategist.tests.unit.services.strategies.test_a_build_turn_reads_once import (
    _thread,
    wdk,
)

__all__ = ["wdk"]


def _text(step_id: str, words: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByText",
        display_name=words,
        parameters={
            "text_expression": StringValue(value=words),
            "text_search_organism": MultiPickValue(values=["Plasmodium berghei ANKA"]),
        },
    )


def _tree(left: str, right: str) -> StrategyStepNode:
    return StrategyStepNode(
        id="step_join",
        search_name="__combine__",
        primary_input=_text("step_a", left),
        secondary_input=_text("step_b", right),
        operator=CombineOp.UNION,
    )


async def test_every_step_of_a_build_whose_read_failed_is_not_built(
    wdk: HoldingWDK, monkeypatch: pytest.MonkeyPatch
) -> None:
    boolean = load_recorded("search_boolean_transcript").json_body()
    serve_recorded_definitions(
        monkeypatch,
        [
            suite_search("search_genes_by_text"),
            WDKSearchResponse.model_validate(boolean).search_data,
        ],
    )
    deps = _thread()
    with turn_reads():
        await apply_operations_and_commit(
            deps=deps, ops=[ReplaceStrategyOp(root=_tree("kinase", "protease"))]
        )
        wdk.refuses_once.add("strategy read")
        outcome = await build_strategy_from_spec(
            deps=deps, root=_tree("rhoptry", "actin")
        )

    read_failed = "PlasmoDB (Plasmodium) did not answer the read of the strategy"
    assert sorted(r.node_id for r in outcome.node_results) == [
        "step_a",
        "step_b",
        "step_join",
    ]
    assert {
        (r.status, r.wdk_step_id, (r.error or "").startswith(read_failed))
        for r in outcome.node_results
    } == {("failed", None, True)}
