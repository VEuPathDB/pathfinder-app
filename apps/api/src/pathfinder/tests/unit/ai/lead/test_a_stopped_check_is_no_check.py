"""A check the guard stopped reports the stop, and leaves no verdict for the turn."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from assistant_core.memory.schemas import MemoryEntryDraft
from pydantic_ai.messages import ToolReturnPart

from pathfinder.ai.graph._lead_events import _summarize_sub_agent_result
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead import verify_dispatch
from pathfinder.ai.lead.answered_strategy import live_tree
from pathfinder.ai.lead.deltas import VerificationDelta, VerificationStopped
from pathfinder.ai.lead.memory_candidates import collect_memory_candidates
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_stream import SubAgentApprovalWait
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.ai.lead.verify_dispatch import run_verification, verification_stopped
from pathfinder.domain.strategy.build_outcome import BuiltCounts
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._budget_stop_turn import (
    built_outcome,
    built_session,
    objection,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    lead_deps,
    pipeline_state,
)

_FINDING = MemoryEntryDraft(
    name="Aedes 24 h responders", summary="70 genes", content={"genes": 70}
)
_EARLIER = objection().model_copy(update={"success": True, "remember": [_FINDING]})
_STOP = PhaseStop(
    role="verification",
    reason=PhaseStopReason.CALL_CAP,
    tool_calls=11,
    tool_name="read_gene_record",
)


def _checked_earlier() -> tuple[PipelineState, StrategySession]:
    """An earlier message built one step and its check passed; a new message follows."""
    session = built_session()
    state = pipeline_state(user_prompt="find the 24 h responders")
    state.user_message_id = uuid4()
    state.record_build(built_outcome())
    state.domain.answered_graph = live_tree(session.get_graph(None))
    state.domain.record_verdict(
        _EARLIER, revision=strategy_revision(state.domain.answered_graph)
    )
    state.user_message_id = uuid4()
    state.user_prompt = "check it again"
    return state, session


async def _dispatch(
    monkeypatch: pytest.MonkeyPatch,
    deps: LeadDeps,
    outcome: VerificationDelta | None,
) -> VerificationDelta | VerificationStopped | SubAgentApprovalWait:
    async def streamed(
        *, deps: LeadDeps, **_kwargs: object
    ) -> VerificationDelta | None:
        deps.last_phase_stop = _STOP if outcome is None else None
        return outcome

    monkeypatch.setattr(verify_dispatch, "stream_sub_agent", streamed)
    return await run_verification(
        deps=deps, parent_tool_call_id="call_verify", reason="check the strategy"
    )


async def test_a_stopped_check_reports_the_stop_and_records_no_verdict(
    monkeypatch: pytest.MonkeyPatch, collector: ChunkCollector
) -> None:
    state, session = _checked_earlier()
    deps = lead_deps(state, strategy_session=session)

    result = await _dispatch(monkeypatch, deps, None)

    assert isinstance(result, VerificationStopped)
    assert result.stop == _STOP
    assert "past its call budget for read_gene_record" in result.summary
    assert state.domain.verification_digest == _EARLIER
    assert collector.data_of("data-evidence-card") == []
    assert state.domain.last_evidence_card is None
    assert state.turn_markers.verified is False


async def test_a_stopped_check_leaves_the_turn_unchecked(
    monkeypatch: pytest.MonkeyPatch, collector: ChunkCollector
) -> None:
    """An earlier verdict on the same strategy is not this turn's finding."""
    del collector
    state, session = _checked_earlier()
    deps = lead_deps(state, strategy_session=session)

    await _dispatch(monkeypatch, deps, None)
    record = turn_record(replace(run_context_for(deps), retries={}))

    assert state.turn_verdict == _EARLIER
    assert state.checked_verdict is None
    assert record.facts.stopped_check == _STOP.render()
    assert record.last_phase_stop == _STOP
    assert [
        key for _, key in collect_memory_candidates(state, counts=BuiltCounts())
    ] == []


async def test_a_check_that_finishes_after_a_stopped_one_is_the_turns_finding(
    monkeypatch: pytest.MonkeyPatch, collector: ChunkCollector
) -> None:
    del collector
    state, session = _checked_earlier()
    deps = lead_deps(state, strategy_session=session)
    await _dispatch(monkeypatch, deps, None)

    result = await _dispatch(monkeypatch, deps, VerificationDelta(digest=_EARLIER))

    assert isinstance(result, VerificationDelta)
    assert state.checked_verdict == result.digest
    assert [
        key for _, key in collect_memory_candidates(state, counts=BuiltCounts())
    ] == [f"knowledge:{state.conversation_id.hex}:0"]


@pytest.mark.parametrize("serialized", [False, True])
def test_the_dispatch_card_of_a_stopped_check_says_it_stopped(serialized: bool) -> None:
    stopped = verification_stopped(_STOP)
    content = stopped.model_dump(mode="json") if serialized else stopped
    part = ToolReturnPart(
        tool_name="verify_strategy", content=content, tool_call_id="c1"
    )

    assert _summarize_sub_agent_result("verify_strategy", part) == (
        "Stopped past its call budget for read_gene_record"
    )


class _CheckRaisedError(Exception):
    """A failure of the check before it returns its digest."""


async def test_a_check_that_raises_leaves_the_turn_unchecked(
    monkeypatch: pytest.MonkeyPatch, collector: ChunkCollector
) -> None:
    """An earlier verdict on the same strategy is not this turn's finding."""
    del collector
    state, session = _checked_earlier()
    deps = lead_deps(state, strategy_session=session)

    async def raises(**_kwargs: object) -> VerificationDelta | None:
        raise _CheckRaisedError

    monkeypatch.setattr(verify_dispatch, "stream_sub_agent", raises)
    with pytest.raises(_CheckRaisedError):
        await run_verification(
            deps=deps, parent_tool_call_id="call_verify", reason="check the strategy"
        )

    assert (state.turn_verdict, state.checked_verdict) == (_EARLIER, None)
