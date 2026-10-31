from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import pytest
import respx
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKStepTree, get_site

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies.reconcile import reconcile_sync_state_with_wdk
from pathfinder.services.strategies.sync import sync_strategy_for_site
from pathfinder.services.strategies.sync_state import WDKSyncState

_USER = 1000000104
_STRATEGY = 214648770
_SIGNAL, _GO, _JOIN = 227290990, 227291030, 227291040
_NAME = "Plasmodium Falciparum 3D7 Signal Peptide Prediction"
_DESCRIBED = "Find transcript results for Predicted Signal Peptide."


def _strategy(tree: dict[str, object]) -> dict[str, object]:
    return {
        "strategyId": _STRATEGY,
        "name": _NAME,
        "description": "",
        "rootStepId": tree["stepId"],
        "recordClassName": "transcript",
        "isSaved": False,
        "isPublic": False,
        "isDeleted": False,
        "isExample": False,
        "isValid": True,
        "estimatedSize": -1,
        "stepTree": tree,
        "steps": {
            str(_SIGNAL): {
                "id": _SIGNAL,
                "strategyId": _STRATEGY,
                "searchName": "GenesWithSignalPeptide",
                "recordClassName": "transcript",
                "customName": "Predicted Signal Peptide",
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


def _site(
    router: respx.MockRouter, held: dict[str, object]
) -> tuple[respx.Route, respx.Route]:
    site = get_site("plasmodb")
    base = site.base_url
    router.get(f"{site.web_base_url}/app").mock(return_value=httpx.Response(200))
    router.get(f"{base}/users/current").mock(
        return_value=httpx.Response(200, json={"id": _USER, "isGuest": False})
    )
    tree = dict(held)

    def _read(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_strategy(tree))

    def _write(request: httpx.Request) -> httpx.Response:
        tree.clear()
        tree.update(json.loads(request.content)["stepTree"])
        return httpx.Response(204)

    router.get(f"{base}/users/{_USER}/strategies/{_STRATEGY}").mock(side_effect=_read)
    put = router.put(f"{base}/users/{_USER}/strategies/{_STRATEGY}/step-tree").mock(
        side_effect=_write
    )
    patch = router.patch(f"{base}/users/{_USER}/strategies/{_STRATEGY}").mock(
        return_value=httpx.Response(204)
    )
    return put, patch


def _signal_peptides() -> StrategyGraph:
    graph = StrategyGraph("g1", _NAME, "plasmodb")
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


async def _push(held: dict[str, object]) -> tuple[list[object], list[object]]:
    state = WDKSyncState(
        wdk_step_ids={"signal": _SIGNAL},
        wdk_strategy_id=_STRATEGY,
        wdk_step_tree=WDKStepTree.model_validate(held),
    )
    with respx.mock(assert_all_called=False) as router:
        put, patch = _site(router, held)
        await reconcile_sync_state_with_wdk(state, "plasmodb", _STRATEGY)
        await sync_strategy_for_site(
            graph=_signal_peptides(), sync_state=state, site_id="plasmodb"
        )
    return (
        [json.loads(call.request.content) for call in put.calls],
        [json.loads(call.request.content) for call in patch.calls],
    )


@pytest.mark.usefixtures("signed_in")
async def test_a_delete_sends_the_tree_and_the_description_it_leaves() -> None:
    held = {
        "stepId": _JOIN,
        "primaryInput": {"stepId": _SIGNAL},
        "secondaryInput": {"stepId": _GO},
    }

    puts, patches = await _push(held)

    assert puts == [{"stepTree": {"stepId": _SIGNAL}}]
    assert patches == [{"name": _NAME, "description": _DESCRIBED}]


@pytest.mark.usefixtures("signed_in")
async def test_an_unchanged_tree_sends_the_description_the_site_lacks() -> None:
    puts, patches = await _push({"stepId": _SIGNAL})

    assert (puts, patches) == ([], [{"description": _DESCRIBED}])
