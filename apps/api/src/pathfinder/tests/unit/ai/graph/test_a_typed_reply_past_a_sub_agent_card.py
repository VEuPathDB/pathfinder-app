from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded

from pathfinder.ai.lead import sub_agent_tools
from pathfinder.tests.unit.ai.graph._approval_turn import (
    RECOVERY_FINAL,
    Collector,
    deleted_step_ids,
    drive_lead,
    lead_deps,
    lead_state,
    one_call_model,
    script_lead,
    stub_execution_toolset,
    two_delete_model,
    writer,
)

__all__ = ["deleted_step_ids", "stub_execution_toolset", "writer"]


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
    writer.payloads.clear()
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
    assert writer.tool_chunks_for("call_delete_step") == []


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
    writer.payloads.clear()
    second = await drive_lead(
        state=typed_state,
        deps=lead_deps(typed_state),
        writer=writer,
    )

    assert deleted_step_ids == ["s2"]
    assert second.response is not None
    assert "yes, go ahead" not in seen_prompts
    assert writer.tool_chunks_for("call_delete_step") == []


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
    writer.payloads.clear()
    second = await drive_lead(
        state=typed_state,
        deps=lead_deps(typed_state),
        writer=writer,
    )
    second_pending = second.pending_approval
    assert second_pending is not None
    assert second.response is None
    assert deleted_step_ids == []
    assert writer.tool_chunks_for("call_delete_1") == []
    assert writer.tool_chunks_for("call_delete_2") == [
        "tool-input-start",
        "tool-input-available",
        "tool-approval-request",
    ]
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
