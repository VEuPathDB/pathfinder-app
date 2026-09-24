from pydantic import BaseModel
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.ui.vercel_ai.response_types import (
    ToolInputAvailableChunk,
    ToolInputDeltaChunk,
    ToolInputStartChunk,
    ToolOutputAvailableChunk,
)

from pathfinder.ai.graph._lead_events import (
    _SUB_AGENT_TOOL_NAMES,
    _SUMMARY_BY_TOOL,
    _summarize_sub_agent_call_args,
    _summarize_sub_agent_result,
    _truncate_summary,
    is_suppressed_sub_agent_chunk,
)
from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.deltas import (
    EditDelta,
    ExecuteDelta,
    FrameResult,
    RecoveryDelta,
    VerificationDelta,
)
from pathfinder.domain.strategy.build_outcome import BuildOutcome, StepPushFailure
from pathfinder.domain.strategy.constraints import ConstraintKind, OpenQuestion
from pathfinder.domain.strategy.spec_diff import SpecDiff


def test_truncate_short_text_is_unchanged() -> None:
    assert _truncate_summary("short reason", limit=280) == "short reason"


def test_truncate_cuts_at_word_boundary_with_ascii_ellipsis() -> None:
    text = "alpha beta gamma delta epsilon"
    out = _truncate_summary(text, limit=18)
    assert out == "alpha beta..."
    assert out.endswith("...")
    assert chr(0x2026) not in out
    assert len(out) <= 18


def test_truncate_total_length_within_limit() -> None:
    text = "word " * 100
    out = _truncate_summary(text, limit=280)
    assert len(out) <= 280
    assert out.endswith("...")
    # never splits a word: the char before the ellipsis is not mid-token
    assert not out[:-3].endswith(" ")


def test_truncate_single_long_word_has_no_space() -> None:
    out = _truncate_summary("x" * 500, limit=20)
    assert len(out) <= 20
    assert out.endswith("...")


def test_summarize_started_args_truncates_long_reason_on_word_boundary() -> None:
    reason = "User wants to identify P. falciparum genes " * 20
    out = _summarize_sub_agent_call_args({"reason": reason})
    assert len(out) <= 280
    assert out.endswith("...")
    assert chr(0x2026) not in out
    assert not out[:-3].endswith(" ")


def _card(tool_name: str, delta: BaseModel) -> str:
    """The completed card's line for one dispatch that returned this delta."""
    return _summarize_sub_agent_result(
        tool_name, ToolReturnPart(tool_name=tool_name, content=delta, tool_call_id="c1")
    )


def _questions(count: int) -> list[OpenQuestion]:
    return [
        OpenQuestion(
            question=f"Which threshold for criterion {n}?",
            dimension=ConstraintKind.STATISTICAL_THRESHOLD,
            recommended_value="0.05",
        )
        for n in range(count)
    ]


def _digest(*, success: bool, pending: tuple[str, ...] = ()) -> VerificationDigest:
    return VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="61 genes.",
        reason="counts plausible",
        success=success,
        pending_checks=list(pending),
    )


def test_summarize_frame_result_needs_user_counts_questions() -> None:
    delta = FrameResult(disposition="needs_user", open_questions=_questions(3))
    assert _card("frame_problem", delta) == "3 open questions"


def test_summarize_frame_result_spec_ready_uses_summary() -> None:
    delta = FrameResult(disposition="spec_ready", summary="Framed 3 criteria")
    assert _card("frame_problem", delta) == "Framed 3 criteria"


def test_summarize_an_edit_that_needs_the_user_counts_questions() -> None:
    delta = EditDelta(
        diff=SpecDiff(), disposition="needs_user", open_questions=_questions(1)
    )
    assert _card("edit_strategy", delta) == "1 open question"


def test_summarize_an_applied_edit_with_no_summary_says_framed() -> None:
    assert _card("edit_strategy", EditDelta(diff=SpecDiff())) == "Framed"


def test_summarize_recovery_counts_actions() -> None:
    assert _card("recover_failed_steps", RecoveryDelta(actions_taken=["a", "b"])) == (
        "2 recovery actions"
    )
    assert _card("recover_failed_steps", RecoveryDelta(actions_taken=["a"])) == (
        "1 recovery action"
    )


def test_summarize_outcome_with_failures() -> None:
    outcome = BuildOutcome(
        pushed_step_ids=["s1", "s2"],
        failed_steps=[
            StepPushFailure(step_id="s3", search_name="GenesByText", error="422")
        ],
    )
    assert _card("build_strategy", ExecuteDelta(outcome=outcome)) == "Built 2, 1 failed"


def test_summarize_outcome_all_built() -> None:
    outcome = BuildOutcome(pushed_step_ids=["s1"])
    assert _card("build_strategy", ExecuteDelta(outcome=outcome)) == "Built 1 step"


def test_summarize_verification_digest() -> None:
    lines = {
        "passed": _card(
            "verify_strategy", VerificationDelta(digest=_digest(success=True))
        ),
        "objected": _card(
            "verify_strategy", VerificationDelta(digest=_digest(success=False))
        ),
    }
    assert lines == {"passed": "Verified successfully", "objected": "Issues found"}


def test_a_pending_check_is_not_verified_successfully() -> None:
    """The card says what the budget verdict says: a pass with checks pending."""
    delta = VerificationDelta(digest=_digest(success=True, pending=("step_de",)))
    assert _card("verify_strategy", delta) == "Passed, 1 check pending"


def test_an_objection_with_a_pending_check_is_an_objection() -> None:
    delta = VerificationDelta(digest=_digest(success=False, pending=("step_de",)))
    assert _card("verify_strategy", delta) == "Issues found"


def test_a_failed_dispatch_shows_its_error_text() -> None:
    result = ToolReturnPart(
        tool_name="verify_strategy",
        content="The run stopped.",
        tool_call_id="c1",
        outcome="failed",
    )
    assert _summarize_sub_agent_result("verify_strategy", result) == "The run stopped."


def test_suppresses_dispatch_input_start_before_call_event_records_id() -> None:
    # The raw tool-input-start chunk for a sub-agent dispatch is emitted from
    # the model's part events, BEFORE the FunctionToolCallEvent that records
    # the id - so the id-set is still empty. It must be classified and
    # suppressed by tool_name, otherwise the raw "· Running" tool card leaks
    # alongside the data-sub-agent-call card.
    calls: dict[str, str] = {}
    start = ToolInputStartChunk(tool_call_id="c1", tool_name="frame_problem")
    assert is_suppressed_sub_agent_chunk(start, calls) is True
    # Priming: the follow-on chunks carry no tool_name but share the id, so
    # they are suppressed via the id recorded from the start chunk.
    delta = ToolInputDeltaChunk(tool_call_id="c1", input_text_delta="{}")
    assert is_suppressed_sub_agent_chunk(delta, calls) is True
    output = ToolOutputAvailableChunk(tool_call_id="c1", output={"ok": True})
    assert is_suppressed_sub_agent_chunk(output, calls) is True


def test_suppresses_every_dispatch_tool() -> None:
    for name in (
        "frame_problem",
        "build_strategy",
        "recover_failed_steps",
        "verify_strategy",
    ):
        calls: dict[str, str] = {}
        start = ToolInputStartChunk(tool_call_id="x", tool_name=name)
        assert is_suppressed_sub_agent_chunk(start, calls) is True


def test_does_not_suppress_lead_own_tool_chunks() -> None:
    calls: dict[str, str] = {}
    start = ToolInputStartChunk(tool_call_id="c2", tool_name="research_web_search")
    assert is_suppressed_sub_agent_chunk(start, calls) is False
    delta = ToolInputDeltaChunk(tool_call_id="c2", input_text_delta="{}")
    assert is_suppressed_sub_agent_chunk(delta, calls) is False
    output = ToolOutputAvailableChunk(tool_call_id="c2", output={"ok": True})
    assert is_suppressed_sub_agent_chunk(output, calls) is False


def test_input_available_also_classifies_dispatch_by_name() -> None:
    # Robustness: tool-input-available also carries tool_name, so a dispatch
    # is caught even if a start chunk were ever missed.
    calls: dict[str, str] = {}
    avail = ToolInputAvailableChunk(
        tool_call_id="c3", tool_name="verify_strategy", input={}
    )
    assert is_suppressed_sub_agent_chunk(avail, calls) is True
    output = ToolOutputAvailableChunk(tool_call_id="c3", output=None)
    assert is_suppressed_sub_agent_chunk(output, calls) is True


def test_every_dispatch_tool_has_a_card_summary() -> None:
    assert set(_SUMMARY_BY_TOOL) == set(_SUB_AGENT_TOOL_NAMES)
