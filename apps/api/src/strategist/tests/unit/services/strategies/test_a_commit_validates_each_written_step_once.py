from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import (
    CombineOp,
    StrategyAst,
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
)

from strategist.domain.strategy.operations import (
    AddLeafOp,
    AttachNewRoot,
    ReplaceStrategyOp,
    UpdateStepParamsOp,
)
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.services.strategies import commit, organism_params
from strategist.services.strategies.commit import apply_operations_and_commit
from strategist.services.strategies.commit_tree import (
    CommitTarget,
    CommittedTree,
    commit_tree,
)
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from strategist.tests._support.recorded_searches import (
    serve_recorded_definitions,
    serve_recorded_record_types,
    suite_search,
)
from strategist.tests.unit.services.strategies._holding_strategy_api import (
    HoldingWDK,
    serve_the_holding_wdk,
)

_SITE = "plasmodb"
_BERGHEI = "Plasmodium berghei ANKA"


@pytest.fixture
def wdk(monkeypatch: pytest.MonkeyPatch) -> HoldingWDK:
    held = HoldingWDK()
    serve_recorded_definitions(
        monkeypatch,
        [suite_search("search_genes_by_text"), suite_search("search_genes_by_taxon")],
    )
    serve_recorded_record_types(monkeypatch)

    async def _no_marks(*_a: object, **_k: object) -> dict[str, str]:
        return {}

    async def _no_organisms(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(organism_params, "organism_parameters", _no_marks)
    monkeypatch.setattr(organism_params, "step_dataset_organisms", _no_organisms)
    return held


def _text(step_id: str, words: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByText",
        display_name=words,
        parameters={
            "text_expression": StringValue(value=words),
            "text_search_organism": MultiPickValue(values=[_BERGHEI]),
        },
    )


def _taxon(step_id: str, *organisms: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByTaxon",
        display_name=step_id,
        parameters={"organism": MultiPickValue(values=list(organisms))},
    )


def _thread() -> StrategyMutationContext:
    session = StrategySession(site_id=_SITE)
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id=_SITE)
    graph.record_type = "transcript"
    session.graph = graph
    return StrategyMutationContext(
        site_id=_SITE, strategy_session=session, conversation_id=None
    )


async def test_an_edit_of_a_held_leaf_is_pushed_with_no_refusal(
    monkeypatch: pytest.MonkeyPatch, wdk: HoldingWDK
) -> None:
    serve_the_holding_wdk(monkeypatch, wdk)
    deps = _thread()
    await apply_operations_and_commit(
        deps=deps, ops=[ReplaceStrategyOp(root=_text("step_a", "kinase"))]
    )
    held = ensure_sync_state(deps.strategy_session).wdk_step_ids["step_a"]
    wdk.writes.clear()

    result = await apply_operations_and_commit(
        deps=deps,
        ops=[
            UpdateStepParamsOp(
                step_id="step_a",
                parameters={"text_expression": StringValue(value="rhoptry")},
            )
        ],
    )

    assert result.failures == []
    (put,) = wdk.written("PUT", f"/steps/{held}/search-config")
    assert put.body["parameters"]["text_expression"] == "rhoptry"


async def test_a_new_leaf_with_an_open_value_is_a_draft(
    monkeypatch: pytest.MonkeyPatch, wdk: HoldingWDK
) -> None:
    serve_the_holding_wdk(monkeypatch, wdk)
    trees: list[CommittedTree] = []

    async def _kept(
        *,
        site_id: str,
        steps: dict[str, StrategyStep],
        root_id: str,
        old: StrategyAst | None,
        sync_state: WDKSyncState,
        target: CommitTarget,
    ) -> CommittedTree:
        made = await commit_tree(
            site_id=site_id,
            steps=steps,
            root_id=root_id,
            old=old,
            sync_state=sync_state,
            target=target,
        )
        trees.append(made)
        return made

    monkeypatch.setattr(commit, "commit_tree", _kept)
    deps = _thread()

    result = await apply_operations_and_commit(
        deps=deps,
        ops=[AddLeafOp(step=_taxon("step_t"), attach=AttachNewRoot())],
    )

    assert result.failures == []
    assert list(trees[0].drafts) == ["step_t"]
    assert wdk.written("POST") == []


async def test_every_refused_value_of_one_commit_is_returned(
    monkeypatch: pytest.MonkeyPatch, wdk: HoldingWDK
) -> None:
    serve_the_holding_wdk(monkeypatch, wdk)
    graph = StrategyGraph(graph_id="g1", name="Two", site_id=_SITE)
    before = StrategyStepNode(
        id="step_c",
        search_name="__combine__",
        operator=CombineOp.UNION,
        primary_input=_taxon("step_a", _BERGHEI),
        secondary_input=_taxon("step_b", _BERGHEI),
    )
    after = before.model_copy(
        update={
            "primary_input": _taxon("step_a", "Not an organism"),
            "secondary_input": _taxon("step_b", "Nor this one"),
        }
    )
    graph.steps = flatten_tree(after)
    graph.recompute_roots()

    committed = await commit_tree(
        site_id=_SITE,
        steps=graph.steps,
        root_id="step_c",
        old=StrategyAst(record_type="transcript", root=before),
        sync_state=WDKSyncState(wdk_step_ids={"step_a": 1, "step_b": 2, "step_c": 3}),
        target=CommitTarget(name="Two", description=""),
    )

    assert [f.error.split(".")[0] for f in committed.failures] == [
        "organism has no entry 'Not an organism'",
        "organism has no entry 'Nor this one'",
    ]
    assert [f.step_id for f in committed.failures] == ["step_a", "step_b"]
    assert wdk.writes == []


async def test_only_the_open_step_is_a_draft_and_its_sibling_is_pushed(
    monkeypatch: pytest.MonkeyPatch, wdk: HoldingWDK
) -> None:
    serve_the_holding_wdk(monkeypatch, wdk)
    root = StrategyStepNode(
        id="step_c",
        search_name="__combine__",
        operator=CombineOp.UNION,
        primary_input=_taxon("step_a"),
        secondary_input=_taxon("step_b", _BERGHEI),
    )

    committed = await commit_tree(
        site_id=_SITE,
        steps=flatten_tree(root),
        root_id="step_c",
        old=None,
        sync_state=WDKSyncState(),
        target=CommitTarget(name="Two", description=""),
    )

    assert (list(committed.drafts), committed.pushed, committed.skipped) == (
        ["step_a"],
        ["step_b"],
        ["step_c"],
    )
    assert (committed.failures, committed.sync) == ([], None)
    assert wdk.written("POST", "/strategies") == []
