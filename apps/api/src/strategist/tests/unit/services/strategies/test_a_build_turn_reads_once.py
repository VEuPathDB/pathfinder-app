from __future__ import annotations

from collections import Counter
from uuid import uuid4

import pytest
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.wdk import StrategyAPI, WDKSearchConfig, turn_reads
from veupathdb_mcp.wdk import get_estimated_size_for_site

from strategist.ai.tools.standalone._sample_page import sample_page
from strategist.domain.strategy.operations import (
    ReplaceStrategyOp,
    UpdateStepParamsOp,
    UpdateStrategyMetaOp,
)
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.services.strategies import organism_params
from strategist.services.strategies.abandoned_mint import (
    ReleasableMint,
    delete_released_mint,
)
from strategist.services.strategies.commit import apply_operations_and_commit
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.insert_saved import clone_saved_strategy
from strategist.services.strategies.live_counts import read_wdk_step_counts
from strategist.services.strategies.site_counts import (
    read_site_strategy,
    read_step_counts,
)
from strategist.services.strategies.sync_state import ensure_sync_state
from strategist.tests._support.holding_wdk import (
    HoldingWDK,
    holding_strategy_api,
    serve_the_holding_wdk,
)
from strategist.tests._support.recorded_searches import (
    serve_recorded_definitions,
    serve_recorded_record_types,
    suite_search,
)

_SITE = "plasmodb"
_SEARCH = "GenesByText"
_CONTEXT = {
    "text_expression": "kinase",
    "text_search_organism": '["Plasmodium berghei ANKA"]',
}
_STRATEGY_READ = "GET /users/N/strategies/N"
_STEP_REPORT = "POST /users/N/steps/N/reports/standard"
_CONTEXT_READ = f"POST /record-types/transcript/searches/{_SEARCH}"
_REFRESH = (
    f"POST /record-types/transcript/searches/{_SEARCH}/refreshed-dependent-params"
)
_SEARCH_REPORT = f"POST /record-types/transcript/searches/{_SEARCH}/reports/standard"
_WRITES = {
    "POST /users/N/steps": 1,
    "POST /users/N/strategies": 1,
    "PATCH /users/N/strategies/N": 1,
}


@pytest.fixture
def wdk(monkeypatch: pytest.MonkeyPatch) -> HoldingWDK:
    held = HoldingWDK(answer_size=5)
    serve_recorded_definitions(monkeypatch, [suite_search("search_genes_by_text")])
    serve_recorded_record_types(monkeypatch)

    async def _no_marks(*_a: object, **_k: object) -> dict[str, str]:
        return {}

    async def _no_organisms(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(organism_params, "organism_parameters", _no_marks)
    monkeypatch.setattr(organism_params, "step_dataset_organisms", _no_organisms)
    serve_the_holding_wdk(monkeypatch, held)
    api = holding_strategy_api(held)
    monkeypatch.setattr(
        "veupathdb_mcp.wdk.step_size.get_strategy_api", lambda _site_id: api
    )
    monkeypatch.setattr(
        "strategist.ai.tools.standalone._sample_page.get_strategy_api",
        lambda _site_id: api,
    )
    return held


def _thread() -> StrategyMutationContext:
    session = StrategySession(site_id=_SITE)
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id=_SITE)
    graph.record_type = "transcript"
    session.graph = graph
    return StrategyMutationContext(
        site_id=_SITE, strategy_session=session, conversation_id=None
    )


def _leaf() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_a",
        search_name=_SEARCH,
        display_name="kinase",
        parameters={
            "text_expression": StringValue(value="kinase"),
            "text_search_organism": MultiPickValue(values=["Plasmodium berghei ANKA"]),
        },
    )


async def _frame_one_criterion(api: StrategyAPI) -> None:
    client = api.client
    config = WDKSearchConfig(parameters=_CONTEXT)
    for _ in range(8):
        await client.get_search_details_with_params("transcript", _SEARCH, _CONTEXT)
    for _ in range(4):
        await client.get_refreshed_dependent_params(
            "transcript", _SEARCH, "text_expression", _CONTEXT
        )
    for _ in range(2):
        await client.run_search_report("transcript", _SEARCH, config)


async def _build_and_verify(deps: StrategyMutationContext, api: StrategyAPI) -> None:
    await apply_operations_and_commit(deps=deps, ops=[ReplaceStrategyOp(root=_leaf())])
    sync = ensure_sync_state(deps.strategy_session)
    step = sync.wdk_step_ids["step_a"]
    strategy = sync.wdk_strategy_id
    assert strategy is not None
    await get_estimated_size_for_site(_SITE, step, strategy)
    await read_wdk_step_counts(sync, _SITE)
    await api.get_step_count(step)
    await api.get_step_count(step)
    await read_site_strategy(_SITE, strategy)
    await read_step_counts(_SITE, strategy)
    await sample_page(
        _SITE, step, limit=5, attributes=None, record_type="transcript", seed="s"
    )
    await apply_operations_and_commit(
        deps=deps, ops=[UpdateStrategyMetaOp(name="Kinases in P. berghei")]
    )
    await read_wdk_step_counts(sync, _SITE)


async def _a_build_turn(wdk: HoldingWDK) -> Counter[str]:
    api = holding_strategy_api(wdk)
    await _frame_one_criterion(api)
    await _build_and_verify(_thread(), api)
    return wdk.sent


def _reads(sent: Counter[str]) -> dict[str, int]:
    return {
        kind: sent[kind]
        for kind in (
            _STRATEGY_READ,
            _STEP_REPORT,
            _CONTEXT_READ,
            _REFRESH,
            _SEARCH_REPORT,
        )
    }


async def test_without_a_turn_scope_every_read_is_sent(wdk: HoldingWDK) -> None:
    sent = await _a_build_turn(wdk)

    assert _reads(sent) == {
        _STRATEGY_READ: 11,
        _STEP_REPORT: 4,
        _CONTEXT_READ: 8,
        _REFRESH: 4,
        _SEARCH_REPORT: 2,
    }
    assert {kind: sent[kind] for kind in _WRITES} == _WRITES


async def test_a_build_turn_sends_each_read_once_between_writes(
    wdk: HoldingWDK,
) -> None:
    with turn_reads():
        sent = await _a_build_turn(wdk)

    assert _reads(sent) == {
        _STRATEGY_READ: 3,
        _STEP_REPORT: 3,
        _CONTEXT_READ: 1,
        _REFRESH: 1,
        _SEARCH_REPORT: 1,
    }
    assert {kind: sent[kind] for kind in _WRITES} == _WRITES


async def test_a_strategy_saved_on_the_website_during_the_turn_is_not_deleted(
    wdk: HoldingWDK,
) -> None:
    deps = _thread()
    with turn_reads():
        await apply_operations_and_commit(
            deps=deps, ops=[ReplaceStrategyOp(root=_leaf())]
        )
        minted = ensure_sync_state(deps.strategy_session).wdk_strategy_id
        assert minted is not None
        await read_site_strategy(_SITE, minted)
        wdk.strategies[minted]["isSaved"] = True
        await delete_released_mint(
            ReleasableMint(
                conversation_id=uuid4(), site_id=_SITE, wdk_strategy_id=minted
            )
        )

    assert wdk.written("DELETE") == []
    assert wdk.strategies[minted]["isSaved"] is True


async def _revised_on_the_website(
    wdk: HoldingWDK, edit: UpdateStepParamsOp | UpdateStrategyMetaOp
) -> int:
    deps = _thread()
    with turn_reads():
        await apply_operations_and_commit(
            deps=deps, ops=[ReplaceStrategyOp(root=_leaf())]
        )
        sync = ensure_sync_state(deps.strategy_session)
        step = sync.wdk_step_ids["step_a"]
        await read_wdk_step_counts(sync, _SITE)
        wdk.steps[step]["searchConfig"]["parameters"]["text_expression"] = "rhoptry"
        await apply_operations_and_commit(deps=deps, ops=[edit])
    return step


async def test_a_rename_keeps_a_value_the_researcher_set_on_the_website(
    wdk: HoldingWDK,
) -> None:
    step = await _revised_on_the_website(
        wdk, UpdateStrategyMetaOp(name="Kinases in P. berghei")
    )

    assert wdk.written("PUT", f"/steps/{step}/search-config") == []
    assert wdk.steps[step]["searchConfig"]["parameters"]["text_expression"] == "rhoptry"
    assert wdk.strategies[wdk.strategy_of(step) or 0]["name"] == "Kinases in P. berghei"


async def test_an_edit_of_another_value_keeps_the_researchers_value(
    wdk: HoldingWDK,
) -> None:
    step = await _revised_on_the_website(
        wdk,
        UpdateStepParamsOp(
            step_id="step_a",
            parameters={
                "text_search_organism": MultiPickValue(
                    values=["Plasmodium falciparum 3D7"]
                )
            },
        ),
    )

    (put,) = wdk.written("PUT", f"/steps/{step}/search-config")
    assert put.body["parameters"]["text_expression"] == "rhoptry"
    assert put.body["parameters"]["text_search_organism"] == (
        '["Plasmodium falciparum 3D7"]'
    )


async def test_the_turns_own_edit_of_that_value_is_sent(wdk: HoldingWDK) -> None:
    step = await _revised_on_the_website(
        wdk,
        UpdateStepParamsOp(
            step_id="step_a",
            parameters={"text_expression": StringValue(value="protease")},
        ),
    )

    (put,) = wdk.written("PUT", f"/steps/{step}/search-config")
    assert put.body["parameters"]["text_expression"] == "protease"
    assert wdk.steps[step]["searchConfig"]["parameters"]["text_expression"] == (
        "protease"
    )


async def test_a_saved_strategy_is_cloned_as_the_site_holds_it_now(
    wdk: HoldingWDK,
) -> None:
    deps = _thread()
    with turn_reads():
        await apply_operations_and_commit(
            deps=deps, ops=[ReplaceStrategyOp(root=_leaf())]
        )
        sync = ensure_sync_state(deps.strategy_session)
        saved = sync.wdk_strategy_id
        assert saved is not None
        await read_site_strategy(_SITE, saved)
        wdk.strategies[saved]["name"] = "Renamed on the website"
        cloned = await clone_saved_strategy(_SITE, saved)

    assert cloned.name == "Renamed on the website"
