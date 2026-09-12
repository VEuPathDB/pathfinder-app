"""The turn starts from the strategy the graph holds, not the one it framed.

The editor removes a step; the next turn's entry spec loses the criterion that
addressed it, so re-asking for the step is an addition and not a no-op.
"""

from __future__ import annotations

from typing import Any

import pytest
from assistant_core.graph.turn_state import PendingApproval
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead import edit_dispatch, pre_turn
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.domain.strategy.build_outcome import BuildOutcome, NodeResult
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations import GraphOperation
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    lead_runtime,
    pipeline_state,
)

_SIGNAL = "step_3fa0e628"
# An edit writes its new step under the criterion id the model chose.
_TRANSMEMBRANE = "transmembrane_domain"
_COMBINE = "step_b272134c"
_SIGNAL_SEARCH = "GenesBySignalPeptide"
_TRANSMEMBRANE_SEARCH = "GenesByTransmembraneDomains"
_PROMPT = "add the transmembrane step back and intersect it with the signal peptide"


def _signal_step() -> StrategyStepNode:
    return StrategyStepNode(
        id=_SIGNAL, search_name=_SIGNAL_SEARCH, display_name="signal peptide"
    )


def _session_after_the_delete() -> StrategySession:
    """What the editor left: one step, the intersection collapsed away."""
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="signal peptide", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(_signal_step())
    graph.recompute_roots()
    session.graph = graph
    return session


def _recorded_build() -> BuildOutcome:
    """The build the last turn recorded, over the three steps it then held."""
    return BuildOutcome(
        node_results=[
            NodeResult(node_id=_SIGNAL, search_name=_SIGNAL_SEARCH, status="ok"),
            NodeResult(
                node_id=_TRANSMEMBRANE,
                search_name=_TRANSMEMBRANE_SEARCH,
                status="ok",
            ),
            NodeResult(node_id=_COMBINE, search_name=COMBINE_SEARCH_NAME, status="ok"),
        ]
    )


def _framed_spec() -> OperationalSpec:
    """The spec the edit left behind, when the strategy held three steps."""
    return OperationalSpec(
        goal="signal peptide and at least one transmembrane domain",
        criteria=[
            Criterion(
                id=_SIGNAL,
                text="signal peptide",
                search_name=_SIGNAL_SEARCH,
                role="seed",
            ),
            Criterion(
                id=_TRANSMEMBRANE,
                text="at least one transmembrane domain",
                search_name=_TRANSMEMBRANE_SEARCH,
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id=_SIGNAL),
                    StructureNode(kind="leaf", criterion_id=_TRANSMEMBRANE),
                ],
            )
        ),
    )


def _state(spec: OperationalSpec | None = None) -> PipelineState:
    return pipeline_state(
        user_prompt=_PROMPT,
        domain=StrategyDomainState(
            operational_spec=_framed_spec() if spec is None else spec,
            last_build_outcome=_recorded_build(),
        ),
    )


async def _entry_spec() -> OperationalSpec:
    refreshed = await refresh_live_strategy_state(
        _state(), lead_runtime(strategy_session=_session_after_the_delete())
    )
    spec = refreshed.domain.spec_before_turn
    assert spec is not None
    return spec


async def test_the_turn_starts_from_the_one_criterion_the_graph_holds() -> None:
    assert [c.id for c in (await _entry_spec()).criteria] == [_SIGNAL]


async def test_the_entry_spec_states_the_shape_the_graph_states() -> None:
    spec = await _entry_spec()

    assert spec.structure is not None
    assert spec.structure.root == StructureNode(kind="leaf", criterion_id=_SIGNAL)


async def test_a_turn_that_resumes_a_parked_call_keeps_the_spec_it_reached() -> None:
    """The resumed turn's entry spec was recorded by the pass that parked."""
    state = _state()
    state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_1", tool_name="consult_user"
    )

    refreshed = await refresh_live_strategy_state(
        state, lead_runtime(strategy_session=_session_after_the_delete())
    )

    spec = refreshed.domain.operational_spec
    assert spec is not None
    assert [c.id for c in spec.criteria] == [_SIGNAL, _TRANSMEMBRANE]


@pytest.fixture
def sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _sheets(**_kwargs: Any) -> dict[str, frozenset[str]]:
        return {_SIGNAL_SEARCH: frozenset()}

    monkeypatch.setattr(pre_turn, "sheet_params_for_searches", _sheets)


@pytest.mark.usefixtures("sheet")
async def test_a_spec_the_reconciliation_empties_is_derived_from_the_graph() -> None:
    """Reconciling before hydration leaves the entry spec describing the graph."""
    emptied = _framed_spec()
    emptied.criteria = [c for c in emptied.criteria if c.id != _SIGNAL]
    emptied.structure = SpecStructure(
        root=StructureNode(kind="leaf", criterion_id=_TRANSMEMBRANE)
    )

    refreshed = await refresh_live_strategy_state(
        _state(emptied), lead_runtime(strategy_session=_session_after_the_delete())
    )

    spec = refreshed.domain.spec_before_turn
    assert spec is not None
    assert [c.id for c in spec.criteria] == [_SIGNAL]


def _reframed() -> OperationalSpec:
    """FRAME binds the transmembrane criterion again, under the id it had."""
    return _framed_spec()


async def _restoring_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[EditDelta, list[GraphOperation]]:
    committed: list[GraphOperation] = []
    state = _state(_reframed())
    state.domain.spec_before_turn = await _entry_spec()
    deps = lead_deps(state, strategy_session=_session_after_the_delete())

    async def _fake_frame(**_kwargs: Any) -> FrameResult:
        return FrameResult(disposition="spec_ready", summary="reframed")

    async def _fake_commit(**kwargs: Any) -> CommitResult:
        committed.extend(kwargs["ops"])
        return CommitResult(description="restored")

    monkeypatch.setattr(edit_dispatch, "run_frame", _fake_frame)
    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _fake_commit)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)
    delta = await run_edit(deps=deps, parent_tool_call_id="t1", reason="restore it")
    assert isinstance(delta, EditDelta)
    return delta, committed


async def test_the_reframed_criterion_diffs_as_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delta, _ = await _restoring_edit(monkeypatch)

    assert delta.diff.added_count == 1
    added = [c.criterion_id for c in delta.diff.changes if c.disposition == "added"]
    assert added == [_TRANSMEMBRANE]


async def test_the_edit_pushes_the_step_and_the_intersection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, committed = await _restoring_edit(monkeypatch)

    assert [op.kind for op in committed] == ["addLeaf", "addCombine"]


async def test_the_leaf_the_edit_adds_runs_the_transmembrane_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, committed = await _restoring_edit(monkeypatch)

    added = committed[0]
    assert added.kind == "addLeaf"
    assert added.step.search_name == _TRANSMEMBRANE_SEARCH


async def test_the_combine_the_edit_adds_intersects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, committed = await _restoring_edit(monkeypatch)

    combine = committed[1]
    assert combine.kind == "addCombine"
    assert combine.step.operator is CombineOp.INTERSECT
    assert combine.step.search_name == COMBINE_SEARCH_NAME
    assert {combine.left_id, combine.right_id} == {_SIGNAL, _TRANSMEMBRANE}
