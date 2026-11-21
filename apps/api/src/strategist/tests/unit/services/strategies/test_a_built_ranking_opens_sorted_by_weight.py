from __future__ import annotations

import pytest
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StepValidation,
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb_mcp.catalog import ValidatedParams

from strategist.domain.strategy.build_outcome import BuildOutcome
from strategist.services.strategies import spec_build, step_wdk_push
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.record_classes import list_every_search_under
from strategist.tests.unit.ai.tools._strategy_edit_stubs import StubAPI

_BY_WEIGHT = {
    "displayPreferences": {"sortColumns": [{"name": "wdk_weight", "direction": "DESC"}]}
}


def _union(weight: int | None) -> list[StrategyStep]:
    steps = flatten_tree(
        StrategyStepNode(
            id="union",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.UNION,
            primary_input=StrategyStepNode(
                id="a", search_name="GenesByTaxon", wdk_weight=weight
            ),
            secondary_input=StrategyStepNode(
                id="b", search_name="GenesByTaxon", wdk_weight=weight
            ),
        )
    )
    return [steps[step_id] for step_id in ("a", "b", "union")]


async def _built(monkeypatch: pytest.MonkeyPatch, weight: int | None) -> StubAPI:
    api = StubAPI()
    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site: api)
    list_every_search_under(monkeypatch, "transcript")

    async def _validate(ctx: SearchContext, **_kwargs: object) -> ValidatedParams:
        del ctx
        return ValidatedParams(params={}, record_class="transcript")

    async def _push(
        *,
        sync_state: WDKSyncState,
        step: StrategyStep,
        site_id: str,
        record_type: str,
        search_name: str,
        parameters: dict[str, ParamValue],
    ) -> tuple[int | None, StepValidation | None, str | None]:
        del site_id, record_type, search_name, parameters
        sync_state.wdk_step_ids[step.id] = 7000 + len(sync_state.wdk_step_ids)
        return sync_state.wdk_step_ids[step.id], None, None

    monkeypatch.setattr(spec_build, "validate_parameters", _validate)
    monkeypatch.setattr(spec_build, "push_step_to_wdk", _push)
    await spec_build._push_tree_to_wdk(
        nodes=_union(weight),
        site_id="plasmodb",
        sync_state=WDKSyncState(),
        outcome=BuildOutcome(),
    )
    return api


async def test_a_built_ranking_opens_sorted_by_weight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = await _built(monkeypatch, 1)

    assert [
        (
            call.kwargs["step_id"],
            call.kwargs["spec"].model_dump(by_alias=True, exclude_none=True),
        )
        for call in api.named("update_step_properties")
    ] == [(7002, _BY_WEIGHT)]


async def test_an_unweighted_build_keeps_the_sites_sort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = await _built(monkeypatch, None)

    assert api.named("update_step_properties") == []
