"""A kind is the kind of the search it was read for, so a step whose search
changes under the same id is read again, and one that keeps its search is not."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb_mcp.catalog import (
    COMPUTE_QUERY,
    EDA_ANALYSIS_SPEC_PARAM,
    EDA_DATASET_ID_PARAM,
)

from pathfinder.ai.lead import pre_turn
from pathfinder.ai.lead.answered_strategy import analyses_of, live_tree
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations.types import (
    ReplaceStrategyOp,
    UpdateStepParamsOp,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_diff import CriterionChange, SpecDiff
from pathfinder.domain.strategy.spec_to_operations import operations_for
from pathfinder.domain.strategy.step_words import StampedKind, StepWords
from pathfinder.services.eda import analysis_kinds
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.spec_build import build_strategy_from_spec
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.analysis_catalog import (
    DESEQ_SEARCH,
    WGCNA_SEARCH,
    serve_the_catalog,
)
from pathfinder.tests._support.run_context import turn_runtime
from pathfinder.tests.unit.ai.lead._analysis_thread import document
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import install_stub_api

_DATASET = "DS_e973eadd57"
_DESEQ = StampedKind(search_name=DESEQ_SEARCH, kind=AnalysisKind.COMPUTE)


def _eda(step_id: str, search: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=search,
        parameters={
            EDA_DATASET_ID_PARAM: StringValue(value=_DATASET),
            EDA_ANALYSIS_SPEC_PARAM: document("18h", 0.05),
        },
    )


def _session(node: StrategyStepNode, stamped: StampedKind | None) -> StrategySession:
    graph = StrategyGraph("g1", "DE", "plasmodb")
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(node))
    graph.recompute_roots()
    if stamped is not None:
        graph.note_analysis_kinds({node.id: stamped})
    session = StrategySession(site_id="plasmodb")
    session.graph = graph
    session.sync_state = WDKSyncState(wdk_step_ids={node.id: 101}, wdk_strategy_id=42)
    return session


def _graph(session: StrategySession) -> StrategyGraph:
    graph = session.get_graph(None)
    assert graph is not None
    return graph


def _stored(session: StrategySession) -> dict[str, StampedKind]:
    ast = _graph(session).to_strategy_ast()
    assert ast is not None
    return StepWords.of(ast).analysis_kinds


def _ctx(session: StrategySession) -> StrategyMutationContext:
    return StrategyMutationContext(site_id="plasmodb", strategy_session=session)


async def _turn_entry(session: StrategySession) -> None:
    """The stamp every turn entry runs over the stored graph."""
    await pre_turn._stamp_the_analysis_kinds(turn_runtime(strategy_session=session))


async def test_a_build_that_reuses_an_id_under_a_new_search_reads_it_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_stub_api(monkeypatch)
    read = serve_the_catalog(monkeypatch)
    session = _session(_eda("step_de", DESEQ_SEARCH), _DESEQ)

    await build_strategy_from_spec(
        deps=_ctx(session), root=_eda("step_de", WGCNA_SEARCH)
    )

    assert read == [WGCNA_SEARCH]
    assert _stored(session) == {
        "step_de": StampedKind(search_name=WGCNA_SEARCH, kind=AnalysisKind.NONE)
    }
    assert analyses_of(live_tree(_graph(session))) == {}


async def test_an_edit_that_rebinds_the_search_is_read_again_at_the_turn_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_stub_api(monkeypatch)
    read = serve_the_catalog(monkeypatch)
    session = _session(_eda("step_de", DESEQ_SEARCH), _DESEQ)
    after = OperationalSpec(
        criteria=[
            Criterion(
                id="step_de",
                text="WGCNA modules instead",
                search_name=WGCNA_SEARCH,
                resolved_params=dict(_eda("x", WGCNA_SEARCH).parameters),
            )
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_de")
        ),
    )
    diff = SpecDiff(
        changes=[
            CriterionChange(
                criterion_id="step_de", disposition="changed", rebound_search=True
            )
        ]
    )
    [op] = operations_for(diff, after=after, graph=_graph(session))

    await apply_and_commit(deps=_ctx(session), op=op)
    rebound = analyses_of(live_tree(_graph(session)))
    await _turn_entry(session)

    assert rebound == {}
    assert read == [WGCNA_SEARCH]
    assert _stored(session) == {
        "step_de": StampedKind(search_name=WGCNA_SEARCH, kind=AnalysisKind.NONE)
    }
    assert analyses_of(live_tree(_graph(session))) == {}


async def test_a_replaced_strategy_that_keeps_the_search_keeps_the_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_stub_api(monkeypatch)
    read = serve_the_catalog(monkeypatch)
    session = _session(_eda("step_de", DESEQ_SEARCH), _DESEQ)

    await apply_and_commit(
        deps=_ctx(session), op=ReplaceStrategyOp(root=_eda("step_de", DESEQ_SEARCH))
    )
    await _turn_entry(session)

    assert (read, _stored(session)) == ([], {"step_de": _DESEQ})


async def test_a_canvas_value_edit_that_keeps_the_search_keeps_the_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_stub_api(monkeypatch)
    read = serve_the_catalog(monkeypatch)
    session = _session(_eda("step_de", DESEQ_SEARCH), _DESEQ)

    await apply_and_commit(
        deps=_ctx(session),
        op=UpdateStepParamsOp(
            step_id="step_de",
            parameters={EDA_ANALYSIS_SPEC_PARAM: document("18h", 0.01)},
        ),
    )
    await _turn_entry(session)

    assert (read, _stored(session)) == ([], {"step_de": _DESEQ})
    [binding] = analyses_of(live_tree(_graph(session))).values()
    assert binding.significance_threshold == 0.01


async def test_a_catalog_that_fails_to_load_leaves_the_kind_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A thread with no record type resolves it from the catalog, whose loader
    names RuntimeError among its failures; the build still persists."""
    install_stub_api(monkeypatch)
    serve_the_catalog(monkeypatch)

    async def _catalog_down(_site: str, _search: str, _record_type: str | None) -> str:
        msg = "catalog load failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(analysis_kinds, "resolve_search_record_type", _catalog_down)
    session = _session(_eda("step_old", DESEQ_SEARCH), None)
    graph = _graph(session)
    graph.steps.clear()
    graph.recompute_roots()
    graph.record_type = None
    node = _eda("step_new", COMPUTE_QUERY)

    outcome = await build_strategy_from_spec(deps=_ctx(session), root=node)

    assert (outcome.failed_steps, list(graph.steps), _stored(session)) == (
        [],
        ["step_new"],
        {},
    )
