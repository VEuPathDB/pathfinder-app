from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.strategy import (
    CombineOp,
    StepKind,
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.errors import WDKError
from veupathdb.wdk import NewStepSpec, StrategyAPI, WDKIdentifier

from strategist.domain.strategy.session import StrategyGraph
from strategist.services.strategies import step_wdk_push
from strategist.services.strategies._wdk_step_calls import _push_leaf_step
from strategist.services.strategies.step_push_planner import (
    CreateAction,
    StepPushPlan,
)
from strategist.services.strategies.step_wdk_push import (
    PushOutcome,
    push_steps_with_plan,
)
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.record_classes import list_every_search_under
from strategist.tests.unit.ai.tools._strategy_edit_stubs import StubAPI

_BY_WEIGHT = {
    "displayPreferences": {"sortColumns": [{"name": "wdk_weight", "direction": "DESC"}]}
}


async def test_a_new_leaf_carries_its_weight(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[NewStepSpec] = []

    async def record(spec: NewStepSpec, **_kwargs: Any) -> WDKIdentifier:
        sent.append(spec)
        return WDKIdentifier(id=1)

    api = StrategyAPI.__new__(StrategyAPI)
    monkeypatch.setattr(api, "create_step", record)
    step = StrategyStep(
        id="a", kind=StepKind.SEARCH, search_name="GenesByTaxon", wdk_weight=1
    )

    await _push_leaf_step(api, "GenesByTaxon", {}, step, "transcript")

    assert [spec.search_config.wdk_weight for spec in sent] == [1]


def _graph(weight: int | None) -> StrategyGraph:
    root = StrategyStepNode(
        id="union",
        search_name="__combine__",
        operator=CombineOp.UNION,
        primary_input=StrategyStepNode(
            id="a", search_name="GenesByTaxon", wdk_weight=weight
        ),
        secondary_input=StrategyStepNode(
            id="b", search_name="GenesByTaxon", wdk_weight=weight
        ),
    )
    graph = StrategyGraph("g1", "test", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    return graph


async def _push(
    monkeypatch: pytest.MonkeyPatch, api: StubAPI, weight: int | None
) -> PushOutcome:
    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site: api)
    list_every_search_under(monkeypatch, "transcript")

    async def _none(*_args: Any, **_kwargs: Any) -> set[str]:
        return set()

    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", _none)
    return await push_steps_with_plan(
        _graph(weight),
        WDKSyncState(),
        "plasmodb",
        [
            StepPushPlan(step_id=step, action=CreateAction(), reason="test")
            for step in ("a", "b", "union")
        ],
    )


async def _pushed(monkeypatch: pytest.MonkeyPatch, weight: int | None) -> StubAPI:
    api = StubAPI()
    await _push(monkeypatch, api, weight)
    return api


async def test_a_ranked_result_opens_sorted_by_weight_highest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = await _pushed(monkeypatch, 1)

    sorted_steps = [
        (
            call.kwargs["step_id"],
            call.kwargs["spec"].model_dump(by_alias=True, exclude_none=True),
        )
        for call in api.named("update_step_properties")
    ]
    assert sorted_steps == [(api.next_id, _BY_WEIGHT)]


async def test_an_unweighted_result_keeps_the_sites_sort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = await _pushed(monkeypatch, None)

    assert api.named("update_step_properties") == []


async def test_a_sort_the_site_refuses_leaves_the_push_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = StubAPI()

    async def refuse(**_kwargs: Any) -> None:
        down = "PATCH /steps -> HTTP 500: down"
        raise WDKError(down, status=500)

    monkeypatch.setattr(api, "update_step_properties", refuse)

    outcome = await _push(monkeypatch, api, 1)

    assert (sorted(outcome.succeeded), outcome.failures) == (["a", "b", "union"], [])
