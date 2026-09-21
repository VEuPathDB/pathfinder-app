"""An edit that follows a build in the same turn plans against what was built."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import edit_dispatch, sub_agent_dispatch
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.sub_agent_dispatch import build_strategy
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations import GraphOperation
from pathfinder.domain.strategy.operations.apply import ApplyError, apply_operation
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_ANNOTATION = "obp_annotation"
_ORTHOLOG = "ortholog_screen"
_EXPRESSION = "antennal_expression"


def _annotation_spec() -> OperationalSpec:
    """One criterion, bound, with the structure a single-leaf build needs."""
    return OperationalSpec(
        goal="odorant binding proteins",
        criteria=[
            Criterion(
                id=_ANNOTATION,
                text="odorant binding protein annotation",
                search_name="GenesByText",
                role="seed",
                resolved_params={
                    "text_search_organism": MultiPickValue(values=["Anopheles"]),
                    "text_expression": StringValue(value="odorant binding protein"),
                },
            )
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id=_ANNOTATION)
        ),
    )


def _empty_session() -> StrategySession:
    session = StrategySession(site_id="vectorbase")
    graph = StrategyGraph(graph_id="g1", name="OBPs", site_id="vectorbase")
    graph.record_type = "transcript"
    session.add_graph(graph)
    return session


def _deps_before_the_build() -> LeadDeps:
    """A turn entered with the framed spec and an empty strategy."""
    spec = _annotation_spec()
    state = pipeline_state(
        site_id="vectorbase",
        user_prompt="find odorant binding proteins in Anopheles",
        domain=StrategyDomainState(operational_spec=spec),
    )
    state.domain.spec_before_turn = spec.model_copy(deep=True)
    return lead_deps(state, strategy_session=_empty_session())


def _fake_build_writes_the_graph(
    monkeypatch: pytest.MonkeyPatch, session: StrategySession
) -> None:
    """Stand in for the WDK build: the graph holds the tree the spec states."""

    async def _build(**kwargs: Any) -> BuildOutcome:
        root: StrategyStepNode = kwargs["root"]
        graph = session.get_graph(None)
        assert graph is not None
        graph.steps = flatten_tree(root)
        graph.recompute_roots()
        graph.last_step_id = root.id
        return BuildOutcome(pushed_step_ids=list(graph.steps))

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _build)
    monkeypatch.setattr(
        sub_agent_dispatch, "get_stream_writer", lambda: lambda _p: None
    )


async def _built_turn(monkeypatch: pytest.MonkeyPatch) -> LeadDeps:
    """Build the framed spec in this turn, and hand back the turn's deps."""
    deps = _deps_before_the_build()
    _fake_build_writes_the_graph(monkeypatch, deps.runtime.strategy_session)
    await build_strategy(run_context_for(deps))
    return deps


def _built_criterion_id(deps: LeadDeps) -> str:
    spec = deps.state.domain.operational_spec
    assert spec is not None
    (criterion,) = spec.criteria
    return criterion.id


def _committed_ids(deps: LeadDeps) -> list[str]:
    spec = deps.state.domain.operational_spec
    assert spec is not None
    return [c.id for c in spec.criteria]


def _draft_that_adds(deps: LeadDeps, criterion_id: str) -> OperationalSpec:
    """What FRAME leaves behind: every live criterion kept, one leaf added."""
    live = deps.state.domain.operational_spec
    assert live is not None
    draft = live.model_copy(deep=True)
    draft.criteria.append(
        Criterion(
            id=criterion_id,
            text="representative species ortholog screen",
            search_name="GenesByOrthologPattern",
            role="filter",
            resolved_params={"organism": MultiPickValue(values=["Anopheles"])},
        )
    )
    inputs = [
        StructureNode(kind="leaf", criterion_id=cid)
        for cid in [*_committed_ids(deps), criterion_id]
    ]
    draft.structure = SpecStructure(
        root=StructureNode(kind="combine", operator=CombineOp.INTERSECT, inputs=inputs)
    )
    return draft


class EditSeams:
    """The two seams an edit dispatch runs through, under the test's control.

    ``draft`` is what FRAME leaves on the state, ``committed`` the operations
    the commit received, and ``apply_to`` the session the commit writes into.
    """

    def __init__(self, *, apply_to: StrategySession | None, refuse: bool) -> None:
        self.draft: OperationalSpec | None = None
        self.committed: list[GraphOperation] = []
        self.apply_to = apply_to
        self.refuse = refuse

    async def frame(self, **kwargs: Any) -> FrameResult:
        deps: LeadDeps = kwargs["deps"]
        assert self.draft is not None
        deps.state.domain.operational_spec = self.draft
        return FrameResult(disposition="spec_ready", summary="reframed")

    async def commit(self, **kwargs: Any) -> CommitResult:
        if self.refuse:
            msg = "the strategy has no root step to edit"
            raise ApplyError(msg)
        ops: list[GraphOperation] = list(kwargs["ops"])
        self.committed.extend(ops)
        if self.apply_to is not None:
            graph = self.apply_to.get_graph(None)
            assert graph is not None
            for op in ops:
                apply_operation(graph, op)
        return CommitResult(description="edited")

    def dumped(self) -> list[dict[str, Any]]:
        return [op.model_dump(by_alias=True, mode="json") for op in self.committed]


def _fake_the_edit_seams(
    monkeypatch: pytest.MonkeyPatch,
    *,
    apply_to: StrategySession | None = None,
    refuse: bool = False,
) -> EditSeams:
    seams = EditSeams(apply_to=apply_to, refuse=refuse)
    monkeypatch.setattr(edit_dispatch, "run_frame", seams.frame)
    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", seams.commit)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)
    return seams


async def _edit(deps: LeadDeps, seams: EditSeams, draft: OperationalSpec) -> EditDelta:
    seams.draft = draft
    result = await run_edit(deps=deps, parent_tool_call_id="t1", reason="add a filter")
    assert isinstance(result, EditDelta)
    return result


async def test_the_build_renumbers_the_turn_entry_record_onto_its_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The build re-keys the criteria, so the entry record is re-keyed too."""
    deps = await _built_turn(monkeypatch)

    entry = deps.state.domain.spec_before_turn
    assert entry is not None
    assert [c.id for c in entry.criteria] == [_built_criterion_id(deps)]
    assert _built_criterion_id(deps) != _ANNOTATION


async def test_the_ledger_after_a_build_reports_no_dropped_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The re-key is not a change to the spec, so the diff names no casualty."""
    deps = await _built_turn(monkeypatch)

    ledger = derive_ledger(deps.state, deps.intent)
    diff = ledger.frame.spec_diff()

    assert diff is not None
    assert (diff.kept_count, diff.dropped_count) == (1, 0)
    assert diff.structure_changed is False


async def test_the_edit_after_a_build_maps_the_kept_criterion_onto_its_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The kept leaf is the live step, so only the added criterion is built."""
    deps = await _built_turn(monkeypatch)
    built_id = _built_criterion_id(deps)
    seams = _fake_the_edit_seams(monkeypatch)

    delta = await _edit(deps, seams, _draft_that_adds(deps, _ORTHOLOG))

    dumped = seams.dumped()
    assert [op["kind"] for op in dumped] == ["addLeaf", "addCombine"]
    added, combine = dumped
    assert added["step"]["searchName"] == "GenesByOrthologPattern"
    assert {combine["leftId"], combine["rightId"]} == {built_id, added["step"]["id"]}
    assert delta.preserved_step_ids == [built_id]
    assert (delta.diff.kept_count, delta.diff.added_count) == (1, 1)
    assert delta.diff.dropped_count == 0


async def test_the_second_edit_plans_against_the_spec_the_first_pushed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The step the first edit added is live, so the second one keeps it."""
    deps = await _built_turn(monkeypatch)
    built_id = _built_criterion_id(deps)
    seams = _fake_the_edit_seams(monkeypatch, apply_to=deps.runtime.strategy_session)

    await _edit(deps, seams, _draft_that_adds(deps, _ORTHOLOG))
    seams.committed.clear()
    second = await _edit(deps, seams, _draft_that_adds(deps, _EXPRESSION))

    dumped = seams.dumped()
    assert [op["kind"] for op in dumped] == ["addLeaf", "addCombine"]
    assert dumped[0]["step"]["id"] == _EXPRESSION
    assert sorted(second.preserved_step_ids) == sorted([built_id, _ORTHOLOG])
    assert (second.diff.kept_count, second.diff.added_count) == (2, 1)
    assert _committed_ids(deps) == [built_id, _ORTHOLOG, _EXPRESSION]


async def test_the_delta_and_the_ledger_report_the_same_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both diffs run against the entry spec the build re-keyed."""
    deps = await _built_turn(monkeypatch)
    seams = _fake_the_edit_seams(monkeypatch)

    delta = await _edit(deps, seams, _draft_that_adds(deps, _ORTHOLOG))

    ledger_diff = derive_ledger(deps.state, deps.intent).frame.spec_diff()
    assert ledger_diff is not None
    counted = (ledger_diff.kept_count, ledger_diff.added_count)
    assert counted == (delta.diff.kept_count, delta.diff.added_count) == (1, 1)
    assert (ledger_diff.dropped_count, delta.diff.dropped_count) == (0, 0)


async def test_a_refused_edit_puts_back_the_spec_the_dispatch_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal leaves the spec the strategy answers to, keyed by its steps."""
    deps = await _built_turn(monkeypatch)
    built_id = _built_criterion_id(deps)
    seams = _fake_the_edit_seams(monkeypatch, refuse=True)
    seams.draft = _draft_that_adds(deps, _ORTHOLOG)

    with pytest.raises(ModelRetry):
        await run_edit(deps=deps, parent_tool_call_id="t1", reason="add a filter")

    assert _committed_ids(deps) == [built_id]
    assert deps.state.domain.operational_spec == deps.state.domain.spec_before_dispatch
