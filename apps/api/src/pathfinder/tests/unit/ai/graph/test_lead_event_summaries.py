from pydantic_ai.ui.vercel_ai.response_types import (
    ToolInputAvailableChunk,
    ToolInputDeltaChunk,
    ToolInputStartChunk,
    ToolOutputAvailableChunk,
)

from pathfinder.ai.graph._lead_events import (
    _summarize_delta_dict,
    _summarize_sub_agent_call_args,
    _truncate_summary,
    is_suppressed_sub_agent_chunk,
)


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


def test_summarize_frame_result_needs_user_counts_questions() -> None:
    out = _summarize_delta_dict(
        {"disposition": "needs_user", "open_questions": [1, 2, 3]}
    )
    assert out == "3 open questions"


def test_summarize_frame_result_spec_ready_uses_summary() -> None:
    out = _summarize_delta_dict(
        {"disposition": "spec_ready", "summary": "Framed 3 criteria"}
    )
    assert out == "Framed 3 criteria"


def test_summarize_recovery_counts_actions() -> None:
    assert _summarize_delta_dict({"actions_taken": ["a", "b"]}) == "2 recovery actions"
    assert _summarize_delta_dict({"actions_taken": ["a"]}) == "1 recovery action"


def test_summarize_outcome_with_failures() -> None:
    out = _summarize_delta_dict(
        {"outcome": {"pushed_step_ids": [1, 2], "failed_steps": [3]}}
    )
    assert out == "Built 2, 1 failed"


def test_summarize_outcome_all_built() -> None:
    out = _summarize_delta_dict(
        {"outcome": {"pushed_step_ids": [1], "failed_steps": []}}
    )
    assert out == "Built 1 step"


def test_summarize_verification_digest() -> None:
    assert (
        _summarize_delta_dict({"digest": {"success": True}}) == "Verified successfully"
    )
    assert _summarize_delta_dict({"digest": {"success": False}}) == "Issues found"


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
