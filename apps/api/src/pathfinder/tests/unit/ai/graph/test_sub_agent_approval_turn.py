"""A sub-agent approval ends the Lead's turn deferred, and the user's answer
re-enters the sub-agent before the Lead run continues.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.lead import sub_agent_tools
from pathfinder.tests.unit.ai.graph._approval_turn import (
    RECOVERY_FINAL,
    RETIRE_ARGS,
    RETIRE_TOOL,
    VERIFICATION_FINAL,
    Collector,
    consult_and_dispatch_model,
    deleted_step_ids,
    drive_lead,
    holding_a_strategy,
    lead_deps,
    lead_state,
    one_call_model,
    pinned_verification_agent,
    script_lead,
    stub_execution_toolset,
    tool_calls,
    two_delete_model,
    writer,
)

__all__ = ["deleted_step_ids", "stub_execution_toolset", "writer"]


async def test_the_turn_ends_deferred_on_the_sub_agents_approval(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_lead(monkeypatch, "verify_strategy")
    monkeypatch.setattr(
        sub_agent_tools,
        "get_mock_model",
        lambda: one_call_model(
            tool_name=RETIRE_TOOL,
            tool_args=RETIRE_ARGS,
            final_args=VERIFICATION_FINAL,
        ),
    )
    state = lead_state()
    deps = holding_a_strategy(lead_deps(state))

    with pinned_verification_agent(monkeypatch):
        capture = await drive_lead(state=state, deps=deps, writer=writer)

    pending = capture.pending_approval
    assert pending is not None
    assert capture.response is None
    assert pending.phase == "verification"
    assert pending.tool_name == "verify_strategy"
    assert pending.tool_call_id == "call_verify_strategy"
    assert pending.sub_agent is not None
    assert pending.sub_agent.role == "verification"
    inner = pending.sub_agent.approvals[0]
    assert inner.tool_call_id == f"call_{RETIRE_TOOL}"
    assert inner.tool_name == RETIRE_TOOL

    approvals = writer.chunks_of("tool-approval-request")
    assert [c["toolCallId"] for c in approvals] == [f"call_{RETIRE_TOOL}"]
    # The Lead's own dispatch call stays plumbing: it never reaches the client.
    assert all(
        c["toolCallId"] != "call_verify_strategy"
        for c in writer.chunks_of("tool-input-available")
    )
    lead_history = ModelMessagesTypeAdapter.validate_json(pending.prior_messages_json)
    assert any(c.tool_name == "verify_strategy" for c in tool_calls(lead_history))


@pytest.mark.usefixtures("stub_execution_toolset")
async def test_the_answer_finishes_the_sub_agent_and_the_lead_replies(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    deleted_step_ids: list[str],
) -> None:
    script_lead(monkeypatch, "recover_failed_steps")
    monkeypatch.setattr(
        sub_agent_tools,
        "get_mock_model",
        lambda: one_call_model(
            tool_name="delete_step",
            tool_args={"step_id": "s2"},
            final_args=RECOVERY_FINAL,
        ),
    )
    state = lead_state()
    deps = lead_deps(state)
    first = await drive_lead(state=state, deps=deps, writer=writer)
    pending = first.pending_approval
    assert pending is not None
    assert deleted_step_ids == []

    resumed_state = lead_state()
    resumed_state.user_message_id = state.user_message_id
    resumed_state.pending_approval = pending
    resumed_state.approval_responses = {
        "call_delete_step": ToolApprovalResponded(
            id="call_delete_step",
            approved=True,
        ),
    }
    resumed_deps = lead_deps(resumed_state)
    second = await drive_lead(state=resumed_state, deps=resumed_deps, writer=writer)

    assert deleted_step_ids == ["s2"]
    assert second.parked_call_answered is True
    assert second.pending_approval is None
    assert second.response is not None
    assert second.response.prose == "scripted"
    outputs = writer.chunks_of("tool-output-available")
    assert "call_delete_step" in [c["toolCallId"] for c in outputs]
    # The dispatch call is plumbing on both turns, so the client is never left
    # with a tool part it cannot resolve.
    named = {
        chunk.get("toolCallId")
        for kind in (
            "tool-input-start",
            "tool-input-available",
            "tool-output-available",
            "tool-approval-request",
        )
        for chunk in writer.chunks_of(kind)
    }
    assert "call_recover_failed_steps" not in named


@pytest.mark.usefixtures("stub_execution_toolset")
async def test_an_answer_naming_the_dispatch_call_still_answers_the_tool(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    deleted_step_ids: list[str],
) -> None:
    """A client that answers the Lead's dispatch call (the chat debugger does)
    answers the approvals that call is waiting on."""
    script_lead(monkeypatch, "recover_failed_steps")
    monkeypatch.setattr(
        sub_agent_tools,
        "get_mock_model",
        lambda: one_call_model(
            tool_name="delete_step",
            tool_args={"step_id": "s2"},
            final_args=RECOVERY_FINAL,
        ),
    )
    state = lead_state()
    first = await drive_lead(state=state, deps=lead_deps(state), writer=writer)
    pending = first.pending_approval
    assert pending is not None

    resumed_state = lead_state()
    resumed_state.user_message_id = state.user_message_id
    resumed_state.pending_approval = pending
    resumed_state.approval_responses = {
        "call_recover_failed_steps": ToolApprovalResponded(
            id="call_recover_failed_steps",
            approved=True,
        ),
    }
    second = await drive_lead(
        state=resumed_state,
        deps=lead_deps(resumed_state),
        writer=writer,
    )

    assert deleted_step_ids == ["s2"]
    assert second.response is not None
    assert second.pending_approval is None


@pytest.mark.usefixtures("stub_execution_toolset")
async def test_a_second_approval_defers_the_turn_again(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    deleted_step_ids: list[str],
) -> None:
    script_lead(monkeypatch, "recover_failed_steps")
    monkeypatch.setattr(sub_agent_tools, "get_mock_model", two_delete_model)
    state = lead_state()
    deps = lead_deps(state)
    first = await drive_lead(state=state, deps=deps, writer=writer)
    pending = first.pending_approval
    assert pending is not None
    assert pending.sub_agent is not None
    assert pending.sub_agent.approvals[0].tool_call_id == "call_delete_1"

    resumed_state = lead_state()
    resumed_state.user_message_id = state.user_message_id
    resumed_state.pending_approval = pending
    resumed_state.approval_responses = {
        "call_delete_1": ToolApprovalResponded(id="call_delete_1", approved=True),
    }
    second = await drive_lead(
        state=resumed_state,
        deps=lead_deps(resumed_state),
        writer=writer,
    )

    assert deleted_step_ids == ["s1"]
    assert second.response is None
    second_pending = second.pending_approval
    assert second_pending is not None
    assert second_pending.tool_call_id == "call_recover_failed_steps"
    assert second_pending.sub_agent is not None
    assert second_pending.sub_agent.approvals[0].tool_call_id == "call_delete_2"


@pytest.mark.usefixtures("stub_execution_toolset")
async def test_a_typed_denial_denies_the_tool_and_reaches_the_lead(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    deleted_step_ids: list[str],
) -> None:
    """Typing instead of clicking denies the tool once and delivers the text."""
    seen_prompts: list[str] = []
    script_lead(monkeypatch, "recover_failed_steps", seen_prompts)
    monkeypatch.setattr(
        sub_agent_tools,
        "get_mock_model",
        lambda: one_call_model(
            tool_name="delete_step",
            tool_args={"step_id": "s2"},
            final_args=RECOVERY_FINAL,
        ),
    )
    state = lead_state()
    first = await drive_lead(state=state, deps=lead_deps(state), writer=writer)
    pending = first.pending_approval
    assert pending is not None

    typed_state = lead_state()
    typed_state.pending_approval = pending
    typed_state.user_message_id = uuid4()
    typed_state.user_prompt = "no, keep that step"
    second = await drive_lead(
        state=typed_state,
        deps=lead_deps(typed_state),
        writer=writer,
    )

    assert deleted_step_ids == []
    assert second.pending_approval is None
    assert second.response is not None
    assert second.response.prose == "scripted"
    assert "no, keep that step" in seen_prompts
    denied = writer.chunks_of("tool-output-denied")
    assert [c["toolCallId"] for c in denied] == ["call_delete_step"]


@pytest.mark.usefixtures("stub_execution_toolset")
async def test_a_typed_approval_runs_the_tool_and_delivers_no_prompt(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    deleted_step_ids: list[str],
) -> None:
    seen_prompts: list[str] = []
    script_lead(monkeypatch, "recover_failed_steps", seen_prompts)
    monkeypatch.setattr(
        sub_agent_tools,
        "get_mock_model",
        lambda: one_call_model(
            tool_name="delete_step",
            tool_args={"step_id": "s2"},
            final_args=RECOVERY_FINAL,
        ),
    )
    state = lead_state()
    first = await drive_lead(state=state, deps=lead_deps(state), writer=writer)
    pending = first.pending_approval
    assert pending is not None

    typed_state = lead_state()
    typed_state.pending_approval = pending
    typed_state.user_message_id = uuid4()
    typed_state.user_prompt = "yes, go ahead"
    second = await drive_lead(
        state=typed_state,
        deps=lead_deps(typed_state),
        writer=writer,
    )

    assert deleted_step_ids == ["s2"]
    assert second.response is not None
    assert "yes, go ahead" not in seen_prompts


@pytest.mark.usefixtures("stub_execution_toolset")
async def test_a_turn_with_no_answer_never_re_runs_the_dispatch(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    deleted_step_ids: list[str],
) -> None:
    """An unresolved dispatch call would be re-executed by pydantic-ai, so a
    turn that answers nothing keeps the card and runs no sub-agent."""
    script_lead(monkeypatch, "recover_failed_steps")
    monkeypatch.setattr(
        sub_agent_tools,
        "get_mock_model",
        lambda: one_call_model(
            tool_name="delete_step",
            tool_args={"step_id": "s2"},
            final_args=RECOVERY_FINAL,
        ),
    )
    state = lead_state()
    first = await drive_lead(state=state, deps=lead_deps(state), writer=writer)
    pending = first.pending_approval
    assert pending is not None
    started_before = len(writer.chunks_of("data-sub-agent-step"))

    idle_state = lead_state()
    idle_state.user_message_id = state.user_message_id
    idle_state.pending_approval = pending
    second = await drive_lead(
        state=idle_state,
        deps=lead_deps(idle_state),
        writer=writer,
    )

    assert deleted_step_ids == []
    assert second.response is None
    assert second.pending_approval == pending
    assert len(writer.chunks_of("data-sub-agent-step")) == started_before


@pytest.mark.usefixtures("stub_execution_toolset")
async def test_a_consult_beside_a_dispatch_loses_neither(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    deleted_step_ids: list[str],
) -> None:
    """A response that defers both a consult and a dispatch: the sub-agent's
    approval is the pending one, and the consult answer still lands."""
    monkeypatch.setattr(_lead_model, "get_mock_model", consult_and_dispatch_model)
    monkeypatch.setattr(
        sub_agent_tools,
        "get_mock_model",
        lambda: one_call_model(
            tool_name="delete_step",
            tool_args={"step_id": "s2"},
            final_args=RECOVERY_FINAL,
        ),
    )
    state = lead_state()
    first = await drive_lead(state=state, deps=lead_deps(state), writer=writer)
    pending = first.pending_approval
    assert pending is not None
    assert pending.tool_call_id == "call_recover_failed_steps"
    assert pending.sub_agent is not None
    assert pending.sub_agent.approvals[0].tool_call_id == "call_delete_step"

    resumed_state = lead_state()
    resumed_state.user_message_id = state.user_message_id
    resumed_state.pending_approval = pending
    resumed_state.approval_responses = {
        "call_delete_step": ToolApprovalResponded(id="call_delete_step", approved=True),
        "call_consult": ToolApprovalResponded(id="call_consult", approved=True),
    }
    second = await drive_lead(
        state=resumed_state,
        deps=lead_deps(resumed_state),
        writer=writer,
    )

    assert deleted_step_ids == ["s2"]
    assert second.pending_approval is None
    assert second.response is not None
    assert second.response.prose == "scripted"


@pytest.mark.usefixtures("stub_execution_toolset")
async def test_a_click_after_a_typed_reply_delivers_no_stale_text(
    writer: Collector,
    monkeypatch: pytest.MonkeyPatch,
    deleted_step_ids: list[str],
) -> None:
    """The typed reply is spent on the denial that raised the second approval,
    so answering that one carries no leftover message."""
    seen_prompts: list[str] = []
    script_lead(monkeypatch, "recover_failed_steps", seen_prompts)
    monkeypatch.setattr(sub_agent_tools, "get_mock_model", two_delete_model)
    state = lead_state()
    first = await drive_lead(state=state, deps=lead_deps(state), writer=writer)
    pending = first.pending_approval
    assert pending is not None
    assert pending.sub_agent is not None
    assert pending.sub_agent.approvals[0].tool_call_id == "call_delete_1"

    typed_state = lead_state()
    typed_state.pending_approval = pending
    typed_state.user_message_id = uuid4()
    typed_state.user_prompt = "no, keep that step"
    second = await drive_lead(
        state=typed_state,
        deps=lead_deps(typed_state),
        writer=writer,
    )
    second_pending = second.pending_approval
    assert second_pending is not None
    assert second.response is None
    assert deleted_step_ids == []
    assert second_pending.sub_agent is not None
    assert second_pending.sub_agent.approvals[0].tool_call_id == "call_delete_2"

    idle_state = lead_state()
    idle_state.pending_approval = second_pending
    idle_state.user_message_id = typed_state.user_message_id
    idle_state.user_prompt = typed_state.user_prompt
    third = await drive_lead(
        state=idle_state,
        deps=lead_deps(idle_state),
        writer=writer,
    )
    assert third.response is None
    assert third.pending_approval == second_pending
    assert "no, keep that step" not in seen_prompts

    click_state = lead_state()
    click_state.pending_approval = second_pending
    click_state.user_message_id = typed_state.user_message_id
    click_state.user_prompt = typed_state.user_prompt
    click_state.approval_responses = {
        "call_delete_2": ToolApprovalResponded(id="call_delete_2", approved=True),
    }
    fourth = await drive_lead(
        state=click_state,
        deps=lead_deps(click_state),
        writer=writer,
    )

    assert deleted_step_ids == ["s2"]
    assert fourth.response is not None
    assert fourth.pending_approval is None
    assert "no, keep that step" not in seen_prompts
