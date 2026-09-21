"""An edit that follows a delete in the same turn plans against what is left."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import edit_dispatch, frame_dispatch
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.lead_tools import delete_step
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations import GraphOperation
from pathfinder.domain.strategy.spec_diff import CriterionChange
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    leaf,
    session_with,
)

_KEPT = "step_k1"
_DELETED = "step_k2"
_ADDED = "new_filter"


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


def _two_leaf_spec() -> OperationalSpec:
    return OperationalSpec(
        goal="essential kinases",
        criteria=[
            Criterion(id=_KEPT, text="kinase domain", search_name="GenesByTaxon"),
            Criterion(id=_DELETED, text="blood stages", search_name="GenesByTaxon"),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id=_KEPT),
                    StructureNode(kind="leaf", criterion_id=_DELETED),
                ],
            )
        ),
    )


def _turn_over_two_steps() -> RunContext[LeadDeps]:
    """A turn entered on a two-step strategy the spec states, as pre_turn leaves it."""
    session = session_with(combine("step_c1", leaf(_KEPT), leaf(_DELETED)), {})
    ctx = lead_run_context(
        user_prompt="drop the blood stage step and add a domain filter",
        strategy_session=session,
        tool_call_id="call_delete",
    )
    spec = _two_leaf_spec()
    ctx.deps.state.domain.operational_spec = spec
    ctx.deps.state.domain.spec_before_turn = spec.model_copy(deep=True)
    return ctx


def _frame_adds_one_leaf(monkeypatch: pytest.MonkeyPatch) -> None:
    """FRAME keeps the surviving criterion and adds one, in the shared draft."""

    async def _stream(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        draft = agent_deps.agent_state.operational_spec_draft
        draft.criteria.append(
            Criterion(id=_ADDED, text="a domain filter", search_name="GenesByTaxon")
        )
        draft.structure = SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id=_KEPT),
                    StructureNode(kind="leaf", criterion_id=_ADDED),
                ],
            )
        )
        return FrameResult(
            disposition="spec_ready",
            summary="added the filter",
            changes=[CriterionChange(criterion_id=_KEPT, disposition="kept")],
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _stream)


def _fake_the_commit(
    monkeypatch: pytest.MonkeyPatch, committed: list[GraphOperation]
) -> None:
    async def _commit(**kwargs: Any) -> CommitResult:
        committed.extend(kwargs["ops"])
        return CommitResult(description="edited")

    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _commit)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)


async def test_the_delete_commits_a_spec_and_leaves_the_turn_entry_record(
    stub_api: StubAPI,
) -> None:
    """The delete drops the criteria it removed; the entry record is the turn's."""
    ctx = _turn_over_two_steps()

    await delete_step(ctx, step_id=_DELETED)

    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert [c.id for c in spec.criteria] == [_KEPT]
    entry = ctx.deps.state.domain.spec_before_turn
    assert entry is not None
    assert [c.id for c in entry.criteria] == [_KEPT, _DELETED]


async def test_the_edit_after_a_delete_keeps_the_surviving_step_and_adds_one(
    stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The removed criterion is not this edit's to account for."""
    ctx = _turn_over_two_steps()
    await delete_step(ctx, step_id=_DELETED)
    _frame_adds_one_leaf(monkeypatch)
    committed: list[GraphOperation] = []
    _fake_the_commit(monkeypatch, committed)

    delta = await run_edit(deps=ctx.deps, parent_tool_call_id="t1", reason="add it")

    assert isinstance(delta, EditDelta)
    dumped = [op.model_dump(by_alias=True, mode="json") for op in committed]
    assert [op["kind"] for op in dumped] == ["addLeaf", "addCombine"]
    assert delta.preserved_step_ids == [_KEPT]
    assert (
        delta.diff.kept_count,
        delta.diff.added_count,
        delta.diff.dropped_count,
    ) == (
        1,
        1,
        0,
    )
    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert sorted(c.id for c in spec.criteria) == sorted([_KEPT, _ADDED])
    found = ctx.deps.state.domain.spec_before_dispatch
    assert found is not None
    assert [c.id for c in found.criteria] == [_KEPT]
