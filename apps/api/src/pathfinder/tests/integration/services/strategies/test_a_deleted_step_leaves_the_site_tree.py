from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import pytest
import respx
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKStepTree, get_site

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies.sync import sync_strategy_for_site
from pathfinder.services.strategies.sync_state import WDKSyncState

_USER = 1000000104
_STRATEGY = 214648770
_SIGNAL, _GO, _JOIN = 227290990, 227291000, 227291010
_HELD_TREE = {
    "stepId": _JOIN,
    "primaryInput": {"stepId": _SIGNAL},
    "secondaryInput": {"stepId": _GO},
}
_REFUSED = {
    "level": "UNSPECIFIED",
    "isValid": False,
    "errors": {"general": [f"{_GO} is not a valid step ID."], "byKey": {}},
}


def _strategy_after_the_put() -> dict[str, object]:
    return {
        "strategyId": _STRATEGY,
        "name": "Plasmodium Apicoplast Signal Peptide Genes",
        "description": "",
        "rootStepId": _SIGNAL,
        "recordClassName": "transcript",
        "isSaved": False,
        "isPublic": False,
        "isDeleted": False,
        "isExample": False,
        "isValid": True,
        "estimatedSize": -1,
        "leafAndTransformStepCount": 1,
        "nameOfFirstStep": "Predicted Signal Peptide",
        "stepTree": {"stepId": _SIGNAL},
        "steps": {
            str(_SIGNAL): {
                "id": _SIGNAL,
                "strategyId": _STRATEGY,
                "searchName": "GenesWithSignalPeptide",
                "recordClassName": "transcript",
                "customName": "Predicted Signal Peptide",
                "displayName": "Predicted Signal Peptide",
                "estimatedSize": 479,
                "validation": {"level": "SEMANTIC", "isValid": True},
                "searchConfig": {
                    "wdkWeight": 0,
                    "parameters": {
                        "organism": '["Plasmodium falciparum 3D7"]',
                        "signalp_version": "SignalP-6.0",
                    },
                },
            }
        },
    }


@pytest.fixture
def signed_in() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("a-registered-token")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(token)


def _site(router: respx.MockRouter, put: httpx.Response) -> respx.Route:
    site = get_site("plasmodb")
    base = site.base_url
    router.get(f"{site.web_base_url}/app").mock(return_value=httpx.Response(200))
    router.get(f"{base}/users/current").mock(
        return_value=httpx.Response(200, json={"id": _USER, "isGuest": False})
    )
    router.patch(f"{base}/users/{_USER}/strategies/{_STRATEGY}").mock(
        return_value=httpx.Response(204)
    )
    router.get(f"{base}/users/{_USER}/strategies/{_STRATEGY}").mock(
        return_value=httpx.Response(200, json=_strategy_after_the_put())
    )
    router.post(f"{base}/users/{_USER}/strategies").mock(
        return_value=httpx.Response(200, json={"id": 1})
    )
    return router.put(f"{base}/users/{_USER}/strategies/{_STRATEGY}/step-tree").mock(
        return_value=put
    )


def _the_graph_after_the_delete() -> StrategyGraph:
    graph = StrategyGraph(
        "g1", "Plasmodium Apicoplast Signal Peptide Genes", "plasmodb"
    )
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="signal",
            search_name="GenesWithSignalPeptide",
            display_name="Predicted Signal Peptide",
            parameters={
                "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
                "signalp_version": SinglePickValue(value="SignalP-6.0"),
            },
        )
    )
    graph.steps["signal"].record_class = "transcript"
    graph.recompute_roots()
    return graph


def _held() -> WDKSyncState:
    return WDKSyncState(
        wdk_step_ids={"signal": _SIGNAL},
        wdk_strategy_id=_STRATEGY,
        wdk_step_tree=WDKStepTree.model_validate(_HELD_TREE),
        wdk_strategy_name="Plasmodium Apicoplast Signal Peptide Genes",
    )


@pytest.mark.usefixtures("signed_in")
async def test_the_put_after_a_delete_sends_the_tree_without_the_step() -> None:
    state = _held()
    with respx.mock(assert_all_called=False) as router:
        put = _site(router, httpx.Response(204))
        result = await sync_strategy_for_site(
            graph=_the_graph_after_the_delete(), sync_state=state, site_id="plasmodb"
        )

    assert [json.loads(call.request.content) for call in put.calls] == [
        {"stepTree": {"stepId": _SIGNAL}}
    ]
    assert (result.wdk_strategy_id, result.counts) == (_STRATEGY, {"signal": 479})
    assert state.wdk_step_tree == WDKStepTree(step_id=_SIGNAL)


@pytest.mark.usefixtures("signed_in")
async def test_a_put_the_site_refuses_raises_and_mints_no_strategy() -> None:
    state = _held()
    with respx.mock(assert_all_called=False) as router:
        _site(router, httpx.Response(422, json=_REFUSED))
        with pytest.raises(WDKError, match=f"{_GO} is not a valid step ID"):
            await sync_strategy_for_site(
                graph=_the_graph_after_the_delete(),
                sync_state=state,
                site_id="plasmodb",
            )
        minted = [call for call in router.calls if call.request.method == "POST"]

    assert minted == []
    assert (state.wdk_strategy_id, state.wdk_step_tree) == (
        _STRATEGY,
        WDKStepTree.model_validate(_HELD_TREE),
    )
