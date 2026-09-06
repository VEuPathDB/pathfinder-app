"""The seam between the Lead's approval cycle and the runtime's.

The Lead decides which deferred call the turn waits on and what the answer
means for the sub-agent under it. Parking the call, replaying its history and
re-announcing it are the runtime's, so a shared field the Lead builds itself
is a second implementation of the cycle.
"""

from __future__ import annotations

import asyncio
import inspect
from uuid import uuid4

from assistant_core.conversation.serde import build_checkpoint_serde
from assistant_core.graph import approvals
from assistant_core.graph.turn_state import (
    PendingApproval,
    SubAgentApprovalCall,
    SubAgentApprovalPending,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy.session import StrategySession

from pathfinder.ai.graph import _lead_turn
from pathfinder.ai.graph._lead_turn import pending_approval
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.services.research.literature_search import LiteratureSearchService
from pathfinder.services.research.web_search import WebSearchService

# What the runtime parks. The Lead adds only ``sub_agent`` and
# ``user_message_id`` on top of these.
SHARED_FIELDS = {
    "phase",
    "tool_call_id",
    "tool_name",
    "tool_args",
    "prior_messages_json",
}

_CONSULT = ToolCallPart(
    tool_name="consult_user",
    args={"questions": []},
    tool_call_id="call_consult",
)
_DISPATCH = ToolCallPart(
    tool_name="recover_failed_steps",
    args={"reason": "drop the failed step"},
    tool_call_id="call_recover_failed_steps",
)


def _never_factory() -> AsyncSession:
    msg = "db factory should not be called in unit tests"
    raise AssertionError(msg)


def _deps() -> LeadDeps:
    return LeadDeps(
        state=PipelineState(
            conversation_id=uuid4(),
            user_id=uuid4(),
            site_id="plasmodb",
            mode="strategy",
            user_message_id=uuid4(),
        ),
        intent=None,
        runtime=Context(
            site_id="plasmodb",
            user_id=uuid4(),
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=_never_factory,
            web_search_service=WebSearchService(),
            literature_search_service=LiteratureSearchService(),
            cancel_event=asyncio.Event(),
        ),
        retrieved_memories=[],
    )


def _history(call: ToolCallPart) -> list[ModelMessage]:
    return [
        ModelRequest(parts=[UserPromptPart(content="drop the failed step")]),
        ModelResponse(parts=[call]),
    ]


def _stash() -> SubAgentApprovalPending:
    return SubAgentApprovalPending(
        role="execution",
        approvals=[
            SubAgentApprovalCall(
                tool_call_id="call_delete_step",
                tool_name="delete_step",
                args={"step_id": "s2"},
            ),
        ],
        messages_json="[]",
    )


def _shared(parked: PendingApproval) -> dict[str, object]:
    return parked.model_dump(include=SHARED_FIELDS)


def _roundtrip(parked: PendingApproval) -> PendingApproval:
    """The approval as a later turn reads it back out of the checkpoint."""
    serde = build_checkpoint_serde()
    decoded = serde.loads_typed(serde.dumps_typed(parked))
    assert isinstance(decoded, PendingApproval)
    return decoded


def test_the_lead_parks_its_own_approval_through_the_runtime() -> None:
    deps = _deps()
    history = _history(_CONSULT)
    output = DeferredToolRequests(approvals=[_CONSULT])

    parked = pending_approval(output=output, deps=deps, messages=history)
    runtime_parked = approvals.pending_approval(
        output=output,
        phase="lead",
        messages=history,
    )

    assert parked is not None
    assert runtime_parked is not None
    assert _shared(parked) == _shared(runtime_parked)
    assert parked.user_message_id == deps.state.user_message_id


def test_the_lead_parks_a_dispatch_through_the_runtime() -> None:
    """A dispatch is not in ``approvals``, so the Lead selects it and parks it
    through the same builder."""
    deps = _deps()
    deps.pending_sub_agent_approvals = {"call_recover_failed_steps": _stash()}
    history = _history(_DISPATCH)
    output = DeferredToolRequests(calls=[_DISPATCH])

    parked = pending_approval(output=output, deps=deps, messages=history)

    assert parked is not None
    assert _shared(parked) == _shared(
        approvals.parked_call(call=_DISPATCH, phase="build", messages=history),
    )


def test_the_lead_defines_no_runtime_cycle_helper() -> None:
    """Replaying the history and re-announcing the parked call are the
    runtime's; a copy under another name is a second implementation."""
    defined = {
        name
        for name, value in vars(_lead_turn).items()
        if inspect.isfunction(value) and value.__module__ == _lead_turn.__name__
    }

    assert defined.isdisjoint({"resume_message_history", "resume_deferred_hint"})


def test_a_parked_dispatch_survives_the_checkpoint_it_waits_in() -> None:
    """The turn that answers reads the approval back from a checkpoint, so the
    runtime's resume helpers must work on the decoded value."""
    deps = _deps()
    deps.pending_sub_agent_approvals = {"call_recover_failed_steps": _stash()}
    parked = pending_approval(
        output=DeferredToolRequests(calls=[_DISPATCH]),
        deps=deps,
        messages=_history(_DISPATCH),
    )
    assert parked is not None

    decoded = _roundtrip(parked)

    assert decoded.sub_agent is not None
    assert decoded.sub_agent.approvals[0].tool_call_id == "call_delete_step"
    assert decoded.user_message_id == deps.state.user_message_id
    assert approvals.deferred_hint(decoded).tool_name == "recover_failed_steps"
    assert len(approvals.resume_history(decoded)) == 2
    results = approvals.approval_results(
        decoded,
        {
            "call_recover_failed_steps": ToolApprovalResponded(
                id="call_recover_failed_steps",
                approved=True,
            ),
        },
    )
    assert results is not None
    assert results.approvals == {"call_recover_failed_steps": True}
