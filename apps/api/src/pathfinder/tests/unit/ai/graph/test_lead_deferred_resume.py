"""The deferred-tool (consult_user) resume must replay the FULL run history.

When the Lead's first action is the deferred tool, ``new_messages()`` holds
only the assistant ``ToolCallPart`` with no leading ``ModelRequest`` — which
pydantic-ai rejects on resume as 'message history is empty'. ``_absorb_run_result``
must capture ``all_messages()`` (request + tool call) into ``prior_messages_json``.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import (
    SubAgentApprovalCall,
    SubAgentApprovalPending,
)
from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.usage import RunUsage

from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_turn import (
    ConcurrentSubAgentApprovalsError,
    pending_approval,
)
from pathfinder.ai.graph.lead_node import _absorb_run_result
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database


class _FakeResult:
    def __init__(
        self,
        *,
        all_msgs: list[Any],
        new_msgs: list[Any],
        output: Any,
    ) -> None:
        self._all = all_msgs
        self._new = new_msgs
        self.output = output
        self.response = SimpleNamespace(
            finish_reason=None,
            model_name="openai:gpt-5-mini",
            provider_name=None,
            provider_url=None,
        )
        self.usage = RunUsage()

    def all_messages(self) -> list[Any]:
        return self._all

    def new_messages(self) -> list[Any]:
        return self._new


def _deps() -> LeadDeps:
    return LeadDeps(
        state=PipelineState(
            conversation_id=uuid4(),
            user_id=uuid4(),
            site_id="plasmodb",
            mode="strategy",
        ),
        intent=None,
        runtime=Context(
            site_id="plasmodb",
            user_id=uuid4(),
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
        ),
        retrieved_memories=[],
    )


def test_deferred_resume_history_includes_user_request() -> None:
    call = ToolCallPart(
        tool_name="consult_user", args={"questions": []}, tool_call_id="c1"
    )
    user_req = ModelRequest(parts=[UserPromptPart(content="build it")])
    consult_resp = ModelResponse(parts=[call])
    result = _FakeResult(
        # new_messages() lacks the leading ModelRequest (Lead's first move was
        # the deferred tool); all_messages() carries it.
        all_msgs=[user_req, consult_resp],
        new_msgs=[consult_resp],
        output=DeferredToolRequests(approvals=[call]),
    )
    capture = _LeadRunCapture()
    event: Any = SimpleNamespace(result=result)
    _absorb_run_result(event, capture, _deps())

    assert capture.pending_approval is not None
    assert capture.pending_approval.phase == "lead"
    assert capture.pending_approval.sub_agent is None
    history = ModelMessagesTypeAdapter.validate_json(
        capture.pending_approval.prior_messages_json
    )
    # The fix: the persisted resume history starts with the user request, so
    # pydantic-ai can match the deferred result to the consult tool call.
    assert len(history) == 2
    assert isinstance(history[0], ModelRequest)
    assert isinstance(history[1], ModelResponse)


def _stash(role: str, tool_call_id: str) -> SubAgentApprovalPending:
    return SubAgentApprovalPending(
        role=role,
        approvals=[
            SubAgentApprovalCall(
                tool_call_id=f"inner_for_{tool_call_id}",
                tool_name="delete_step",
                args={"step_id": "s2"},
            ),
        ],
        messages_json="[]",
    )


def _deferred_dispatch(tool_name: str, tool_call_id: str, reason: str) -> ToolCallPart:
    return ToolCallPart(
        tool_name=tool_name,
        args={"reason": reason},
        tool_call_id=tool_call_id,
    )


def test_a_dispatch_is_paired_with_its_own_suspended_run() -> None:
    deps = _deps()
    deps.pending_sub_agent_approvals = {
        "call_a": _stash("frame", "call_a"),
        "call_b": _stash("verification", "call_b"),
    }
    output = DeferredToolRequests(
        calls=[_deferred_dispatch("verify_strategy", "call_b", "check the counts")],
    )

    pending = pending_approval(output=output, deps=deps, messages=[])

    assert pending is not None
    assert pending.phase == "verification"
    assert pending.tool_call_id == "call_b"
    assert pending.tool_args["reason"] == "check the counts"
    assert pending.sub_agent is not None
    assert pending.sub_agent.role == "verification"
    assert pending.sub_agent.approvals[0].tool_call_id == "inner_for_call_b"


def test_a_deferred_dispatch_outranks_a_consult_approval() -> None:
    deps = _deps()
    deps.pending_sub_agent_approvals = {"call_b": _stash("execution", "call_b")}
    consult = ToolCallPart(
        tool_name="consult_user",
        args={"questions": []},
        tool_call_id="call_consult",
    )
    output = DeferredToolRequests(
        approvals=[consult],
        calls=[_deferred_dispatch("recover_failed_steps", "call_b", "drop s2")],
    )

    pending = pending_approval(output=output, deps=deps, messages=[])

    assert pending is not None
    assert pending.phase == "build"
    assert pending.tool_call_id == "call_b"
    assert pending.sub_agent is not None


def test_two_deferred_dispatches_fail_loudly() -> None:
    deps = _deps()
    deps.pending_sub_agent_approvals = {
        "call_a": _stash("frame", "call_a"),
        "call_b": _stash("verification", "call_b"),
    }
    output = DeferredToolRequests(
        calls=[
            _deferred_dispatch("frame_problem", "call_a", "frame it"),
            _deferred_dispatch("verify_strategy", "call_b", "check it"),
        ],
    )

    with pytest.raises(ConcurrentSubAgentApprovalsError) as excinfo:
        pending_approval(output=output, deps=deps, messages=[])

    assert "call_a" in str(excinfo.value)
    assert "call_b" in str(excinfo.value)
