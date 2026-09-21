"""A frame that follows a clear in the same turn starts from an empty workspace."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.frame_dispatch import run_frame
from pathfinder.ai.lead.lead_tools import clear_strategy
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import conversation
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    combine,
    leaf,
    session_with,
)

_FIRST = "step_k1"
_SECOND = "step_k2"
_FRESH = "phosphatase_domain"
_OLD_GOAL = "essential kinases"
_REQUEST = "scrap all of it and start over on ring stage phosphatases"


@pytest.fixture
def no_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _persisted(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        conversation, "persist_strategy_ast_to_conversation", _persisted
    )


def _two_leaf_spec() -> OperationalSpec:
    return OperationalSpec(
        goal=_OLD_GOAL,
        criteria=[
            Criterion(id=_FIRST, text="kinase domain", search_name="GenesByTaxon"),
            Criterion(id=_SECOND, text="blood stages", search_name="GenesByTaxon"),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id=_FIRST),
                    StructureNode(kind="leaf", criterion_id=_SECOND),
                ],
            )
        ),
    )


def _turn_over_two_steps() -> RunContext[LeadDeps]:
    """A turn entered on a two-step strategy the spec states."""
    session = session_with(combine("step_c1", leaf(_FIRST), leaf(_SECOND)), {})
    ctx = lead_run_context(
        user_prompt=_REQUEST,
        strategy_session=session,
        tool_call_id="call_clear",
    )
    spec = _two_leaf_spec()
    ctx.deps.state.domain.operational_spec = spec
    ctx.deps.state.domain.spec_before_turn = spec.model_copy(deep=True)
    return ctx


class FrameSpy:
    """A fresh FRAME pass: it records the workspace it found and binds one criterion."""

    def __init__(self) -> None:
        self.criteria_found: list[str] = []
        self.goal_found = ""

    async def __call__(self, **kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        draft = agent_deps.agent_state.operational_spec_draft
        self.criteria_found = [c.id for c in draft.criteria]
        self.goal_found = draft.goal
        draft.criteria = [
            Criterion(
                id=_FRESH, text="a phosphatase domain", search_name="GenesByTaxon"
            )
        ]
        draft.structure = SpecStructure(
            root=StructureNode(kind="leaf", criterion_id=_FRESH)
        )
        return FrameResult(disposition="spec_ready", summary="bound the domain")


def _frame_spy(monkeypatch: pytest.MonkeyPatch) -> FrameSpy:
    spy = FrameSpy()
    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", spy)
    return spy


@pytest.mark.usefixtures("no_persistence")
async def test_the_clear_leaves_no_spec_and_keeps_the_turn_entry_record() -> None:
    """The cleared thread states no criteria; the entry record is still the turn's."""
    ctx = _turn_over_two_steps()

    await clear_strategy(ctx, confirm=True)

    assert ctx.deps.state.domain.operational_spec is None
    entry = ctx.deps.state.domain.spec_before_turn
    assert entry is not None
    assert [c.id for c in entry.criteria] == [_FIRST, _SECOND]


@pytest.mark.usefixtures("no_persistence")
async def test_an_unconfirmed_clear_leaves_the_spec_standing() -> None:
    ctx = _turn_over_two_steps()

    with pytest.raises(ModelRetry, match="VALIDATION_ERROR"):
        await clear_strategy(ctx, confirm=False)

    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert [c.id for c in spec.criteria] == [_FIRST, _SECOND]


@pytest.mark.usefixtures("no_persistence")
async def test_a_frame_after_a_clear_frames_an_empty_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cleared criteria are not the new pass's to account for."""
    ctx = _turn_over_two_steps()
    await clear_strategy(ctx, confirm=True)
    spy = _frame_spy(monkeypatch)

    result = await run_frame(
        deps=ctx.deps, parent_tool_call_id="t1", work_order="frame it"
    )

    assert isinstance(result, FrameResult)
    assert spy.criteria_found == []
    assert spy.goal_found == _REQUEST
    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert [c.id for c in spec.criteria] == [_FRESH]
    assert ctx.deps.state.domain.spec_before_dispatch is None


@pytest.mark.usefixtures("no_persistence")
async def test_the_ledger_reports_the_cleared_criteria_as_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clear plus a fresh frame is every entry criterion dropped and one added."""
    ctx = _turn_over_two_steps()
    await clear_strategy(ctx, confirm=True)
    _frame_spy(monkeypatch)

    await run_frame(deps=ctx.deps, parent_tool_call_id="t1", work_order="frame it")

    diff = derive_ledger(ctx.deps.state, None).frame.diff
    assert diff is not None
    assert (diff.dropped_count, diff.added_count, diff.kept_count) == (2, 1, 0)
