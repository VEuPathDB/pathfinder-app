"""WDK holds a nested group under the name of the steps inside it."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import (
    ColocationParams,
    CombineOp,
    StrategyAst,
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.step_words import StepWords
from pathfinder.services.strategies import spec_build, step_wdk_push
from pathfinder.services.strategies.step_push_planner import (
    PatchAction,
    plan_step_pushes,
)
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import StubAPI

_NAME = "Union: PEXEL motif, Signal peptide"
_WDK_IDS = {
    "taxon": 440537303,
    "pexel": 440537313,
    "signal": 440537323,
    "exported": 440537333,
    "root": 440537343,
}


def _tree(
    *, signal: str = "Signal peptide", named: str | None = None
) -> StrategyStepNode:
    return StrategyStepNode(
        id="root",
        search_name="__combine__",
        operator=CombineOp.INTERSECT,
        display_name="Intersect",
        expanded_name=named,
        primary_input=StrategyStepNode(
            id="taxon", search_name="GenesByTaxon", display_name="Genes by taxon"
        ),
        secondary_input=StrategyStepNode(
            id="exported",
            search_name="__combine__",
            operator=CombineOp.UNION,
            display_name="Union",
            primary_input=StrategyStepNode(
                id="pexel", search_name="GenesByMotifSearch", display_name="PEXEL motif"
            ),
            secondary_input=StrategyStepNode(
                id="signal", search_name="GenesWithSignalPeptide", display_name=signal
            ),
        ),
    )


def _root(named: str | None) -> StrategyStep:
    return flatten_tree(_tree(named=named))["root"]


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    stub = StubAPI()
    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site: stub)
    return stub


async def test_the_create_patches_the_name_onto_the_group_s_combine(
    api: StubAPI,
) -> None:
    await step_wdk_push.push_step_to_wdk(
        sync_state=WDKSyncState(wdk_step_ids=dict(_WDK_IDS)),
        step=_root(_NAME),
        site_id="plasmodb",
        record_type="transcript",
        search_name="__combine__",
        parameters={},
    )

    (patch,) = api.named("update_step_properties")
    assert patch.kwargs["spec"].expanded_name == _NAME
    assert patch.kwargs["spec"].expanded is None


async def test_a_colocation_over_a_group_carries_its_name(api: StubAPI) -> None:
    step = _root(_NAME).model_copy(
        update={"operator": CombineOp.COLOCATE, "colocation_params": ColocationParams()}
    )

    await step_wdk_push.push_step_to_wdk(
        sync_state=WDKSyncState(wdk_step_ids=dict(_WDK_IDS)),
        step=step,
        site_id="plasmodb",
        record_type="transcript",
        search_name="__combine__",
        parameters={},
    )

    assert [call.name for call in api.calls] == [
        "create_transform_step",
        "update_step_properties",
    ]
    assert api.calls[1].kwargs["spec"].expanded_name == _NAME


async def test_a_combine_over_no_group_patches_nothing(api: StubAPI) -> None:
    await step_wdk_push.push_step_to_wdk(
        sync_state=WDKSyncState(wdk_step_ids=dict(_WDK_IDS)),
        step=_root(None),
        site_id="plasmodb",
        record_type="transcript",
        search_name="__combine__",
        parameters={},
    )

    assert api.named("update_step_properties") == []


def test_a_new_group_name_is_a_name_write() -> None:
    plan = plan_step_pushes(
        old_ast=StrategyAst(record_type="transcript", root=_tree(named=_NAME)),
        new_ast=StrategyAst(
            record_type="transcript",
            root=_tree(signal="SignalP", named="Union: PEXEL motif, SignalP"),
        ),
        existing_wdk_ids=dict(_WDK_IDS),
    )

    assert {entry.step_id: entry.action for entry in plan}["root"] == PatchAction(
        search_config=False, name=True
    )


async def test_the_name_write_carries_the_group_name(api: StubAPI) -> None:
    failure = await step_wdk_push._execute_patch(
        WDKSyncState(wdk_step_ids=dict(_WDK_IDS)),
        "plasmodb",
        _root(_NAME),
        "transcript",
        PatchAction(search_config=False, name=True),
    )

    assert failure is None
    (patch,) = api.named("update_step_properties")
    assert patch.kwargs["step_id"] == _WDK_IDS["root"]
    assert patch.kwargs["spec"].custom_name == "Intersect"
    assert patch.kwargs["spec"].expanded_name == _NAME


def test_the_build_names_the_group_in_the_graph() -> None:
    graph = StrategyGraph("g1", "test", "plasmodb")

    spec_build._replace_graph_contents(
        graph,
        _tree(),
        sync_state=WDKSyncState(),
        description=None,
        step_words=StepWords(),
    )

    assert graph.steps["root"].expanded_name == _NAME
