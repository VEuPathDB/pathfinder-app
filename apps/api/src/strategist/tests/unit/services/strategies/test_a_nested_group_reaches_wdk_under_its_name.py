"""WDK holds a nested group under the name of the steps inside it."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import (
    ColocationParams,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
)
from veupathdb.wdk import PatchStepSpec

from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.step_words import StepWords
from strategist.services.strategies import spec_build
from strategist.services.strategies.step_push_planner import (
    PatchAction,
    plan_step_pushes,
)
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.wdk_write_stubs import commit_against, held_as
from strategist.tests.unit.ai.tools._strategy_edit_stubs import StubAPI

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


_INPUTS = {k: v for k, v in _WDK_IDS.items() if k != "root"}


async def _created(monkeypatch: pytest.MonkeyPatch, root: StrategyStepNode) -> StubAPI:
    api = StubAPI()
    before = root.model_copy(update={"id": "before"})
    await commit_against(monkeypatch, api, root, before=before, held=_INPUTS)
    return api


async def test_the_create_patches_the_name_onto_the_group_s_combine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = await _created(monkeypatch, _tree(named=_NAME))

    (patch,) = api.named("update_step_properties")
    assert patch.kwargs["spec"].expanded_name == _NAME
    assert patch.kwargs["spec"].expanded is True


async def test_a_colocation_over_a_group_carries_its_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _tree(named=_NAME).model_copy(
        update={"operator": CombineOp.COLOCATE, "colocation_params": ColocationParams()}
    )

    api = await _created(monkeypatch, root)

    assert [call.name for call in api.calls] == [
        "create_transform_step",
        "update_step_properties",
    ]
    assert api.calls[1].kwargs["spec"].expanded_name == _NAME
    assert api.calls[1].kwargs["spec"].expanded is True


async def test_a_combine_over_no_group_patches_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = await _created(monkeypatch, _tree(named=None))

    assert api.named("update_step_properties") == []


def test_a_new_group_name_is_a_name_write() -> None:
    plan = plan_step_pushes(
        old_ast=StrategyAst(record_type="transcript", root=_tree(named=_NAME)),
        new_ast=StrategyAst(
            record_type="transcript",
            root=_tree(signal="SignalP", named="Union: PEXEL motif, SignalP"),
        ),
        existing_wdk_ids=dict(_WDK_IDS),
        held=held_as(StrategyAst(record_type="transcript", root=_tree(named=_NAME))),
    )

    assert {entry.step_id: entry.action for entry in plan}["root"] == PatchAction(
        search_config=False, name=True
    )


async def test_the_name_write_carries_the_group_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = StubAPI()

    committed, _ = await commit_against(
        monkeypatch, api, _tree(named=_NAME), before=_tree(), held=_WDK_IDS
    )

    assert committed.failures == []
    (patch,) = api.named("update_step_properties")
    assert patch.kwargs["step_id"] == _WDK_IDS["root"]
    assert patch.kwargs["spec"].custom_name == "Intersect"
    assert patch.kwargs["spec"].expanded_name == _NAME
    assert patch.kwargs["spec"].expanded is True


async def test_a_name_write_over_no_group_leaves_the_display_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = StubAPI()
    before = _tree().model_copy(update={"display_name": "And"})

    await commit_against(monkeypatch, api, _tree(), before=before, held=_WDK_IDS)

    (patch,) = api.named("update_step_properties")
    assert patch.kwargs["spec"] == PatchStepSpec(custom_name="Intersect")


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
