"""The typed results a sub-agent dispatch hands back to the Lead."""

from __future__ import annotations

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.deltas import (
    ExecuteDelta,
    FrameResult,
    RecoveryDelta,
    VerificationDelta,
)
from pathfinder.domain.strategy.build_outcome import BuildOutcome


def test_frame_result_disposition_default_spec_ready() -> None:
    result = FrameResult(summary="bound 3 criteria")
    assert result.disposition == "spec_ready"
    assert result.open_questions == []


def test_frame_result_needs_user_carries_questions() -> None:
    result = FrameResult(
        summary="one open slot",
        disposition="needs_user",
        open_questions=["Which RNA-seq dataset?"],
    )
    assert result.disposition == "needs_user"
    assert result.open_questions == ["Which RNA-seq dataset?"]


def test_execute_delta_carries_outcome() -> None:
    outcome = BuildOutcome(pushed_step_ids=["s1"], wdk_strategy_id=42, root_count=152)
    delta = ExecuteDelta(outcome=outcome)
    assert delta.outcome.root_count == 152


def test_recovery_delta_is_light() -> None:
    delta = RecoveryDelta(actions_taken=["rebuilt s1"], follow_up_needed=False)
    assert delta.actions_taken == ["rebuilt s1"]
    assert not hasattr(delta, "final_outcome")


def test_verification_delta_carries_digest() -> None:
    digest = VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="all good",
        reason="checks pass",
        success=True,
    )
    delta = VerificationDelta(digest=digest)
    assert delta.digest.success is True
