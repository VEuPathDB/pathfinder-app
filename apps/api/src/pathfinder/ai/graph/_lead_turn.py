"""Turn-level helpers for the Lead node.

Memory retrieval at turn start, and what an answer - the user's click or the
worker's result - means for the run the turn parked. Reading the answer itself
belongs to ``_lead_answers``, the durable park and its partition to
``_lead_durable``, and the cycle's shared mechanics to the runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from assistant_core.graph import approvals
from assistant_core.graph.durable import durable_tool_results
from assistant_core.graph.emit import emit_chunk
from assistant_core.graph.turn_state import (
    ParkedCall,
    PendingApproval,
    PendingDurableCall,
)
from assistant_core.memory.deadline import (
    MemoryStoreTimeoutError,
    memory_store_deadline,
)
from assistant_core.memory.retrieval import RetrievalScope, retrieve_relevant_memories
from assistant_core.memory.store import MemoryStore, StoredMemory
from assistant_core.platform.logging import get_logger
from langgraph.runtime import Runtime
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.tools import (
    DeferredToolApprovalResult,
    DeferredToolRequests,
    DeferredToolResults,
    ToolDenied,
)
from pydantic_ai.ui.vercel_ai.response_types import (
    ToolInputAvailableChunk,
    ToolInputStartChunk,
    ToolOutputDeniedChunk,
)

from pathfinder.ai.graph._lead_answers import (
    answers_for,
    is_pure_approval,
    sibling_answers,
    typed_reply,
    unanswered_inner,
)
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_durable import (
    control_results_answered,
    inner_durable_calls,
    outer_durable_calls,
    split_durable_answers,
)
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.dispatch_resume import SubAgentOutcome, resume_sub_agent
from pathfinder.ai.lead.proposal import PROPOSAL_TOOL, DeclinedProposal
from pathfinder.ai.lead.sub_agent_stream import SubAgentApprovalWait, SubAgentResume
from pathfinder.ai.lead.sub_agent_tools import WIRE_PHASE_BY_ROLE, LeadDeps
from pathfinder.domain.memory import MEMORY_KINDS, STANDING_MEMORY_KINDS

logger = get_logger(__name__)


async def retrieve_memories(
    state: PipelineState,
    runtime: Runtime[Context],
) -> list[StoredMemory]:
    """Fresh-turn cross-thread retrieval."""
    if runtime.context is None or runtime.context.memory_store is None:
        return []
    if not state.user_prompt.strip():
        return []
    mem_store = MemoryStore(store=runtime.context.memory_store)
    try:
        async with memory_store_deadline("memory retrieval"):
            return await retrieve_relevant_memories(
                store=mem_store,
                user_id=state.user_id,
                query=state.user_prompt,
                scope=RetrievalScope(
                    kinds=MEMORY_KINDS,
                    always_kinds=STANDING_MEMORY_KINDS,
                    keep=lambda memory: memory.site_id in (None, state.site_id),
                    top_k=8,
                ),
            )
    except MemoryStoreTimeoutError as exc:
        logger.warning(
            "memory retrieval timed out; the turn runs without memories",
            conversation_id=str(state.conversation_id),
            seconds=exc.seconds,
        )
        return []


class ConcurrentSubAgentApprovalsError(RuntimeError):
    """Two sub-agent dispatches in one Lead response both stopped at an approval."""

    def __init__(self, tool_call_ids: list[str]) -> None:
        super().__init__(
            "Two sub-agent dispatches deferred in one response "
            f"({', '.join(tool_call_ids)}). One suspended run is checkpointed "
            "per turn, so the second would be re-run rather than resumed.",
        )


def pending_approval(
    *,
    output: DeferredToolRequests,
    deps: LeadDeps,
    messages: list[ModelMessage],
) -> PendingApproval | None:
    """The approval a deferred Lead run waits on: the sub-agent call it
    dispatched, else its own tool.

    A dispatch outranks the Lead's own approval, because only the dispatch
    holds a suspended sub-agent run; an unapproved Lead tool is re-collected by
    pydantic-ai on the next run.
    """
    dispatches = [
        call
        for call in output.calls
        if call.tool_call_id in deps.pending_sub_agent_approvals
    ]
    if len(dispatches) > 1:
        raise ConcurrentSubAgentApprovalsError([c.tool_call_id for c in dispatches])
    user_message_id = deps.state.user_message_id
    if dispatches:
        sub_agent = deps.pending_sub_agent_approvals[dispatches[0].tool_call_id]
        parked = approvals.parked_call(
            call=dispatches[0],
            phase=WIRE_PHASE_BY_ROLE[sub_agent.role],
            messages=messages,
        )
        return parked.model_copy(
            update={"sub_agent": sub_agent, "user_message_id": user_message_id},
        )
    own = approvals.pending_approval(output=output, phase="lead", messages=messages)
    if own is None:
        return None
    return own.model_copy(update={"user_message_id": user_message_id})


@dataclass(frozen=True)
class TurnResumption:
    """What the Lead's run re-enters: the parked call it answers, the results
    that answer it, the message to deliver with them, or a further call to
    wait on. A declined proposal re-enters nothing: the turn ends as it stood."""

    parked: ParkedCall | None = None
    results: DeferredToolResults | None = None
    still_pending: PendingApproval | None = None
    still_durable: PendingDurableCall | None = None
    user_prompt: str | None = None
    declined: DeclinedProposal | None = None


_DECLINED_BY_REPLY = "The researcher sent a new message instead of answering the card."


def _declined(deps: LeadDeps, approval: PendingApproval, note: str) -> DeclinedProposal:
    """Record the card the researcher declined, so a later yes asks again."""
    declined = DeclinedProposal.model_validate({**approval.tool_args, "note": note})
    deps.state.domain.declined_proposal = declined
    return declined


def _resolve_proposal(
    state: PipelineState,
    deps: LeadDeps,
    approval: PendingApproval,
) -> TurnResumption:
    """A yes runs the card's edit, and a no ends the turn with no model call.

    A typed approval phrase is a yes. Any other typed message declines the card
    and is delivered to the Lead as the researcher's next message.
    """
    answer: bool | DeferredToolApprovalResult | None = answers_for(
        state, [approval.tool_call_id]
    ).get(approval.tool_call_id)
    typed = typed_reply(state)
    if answer is None and typed is not None and is_pure_approval(typed):
        answer = True
    if answer is True:
        return TurnResumption(
            parked=approval,
            results=DeferredToolResults(approvals={approval.tool_call_id: True}),
        )
    if answer is not None:
        response = state.approval_responses[approval.tool_call_id]
        return TurnResumption(
            parked=approval,
            declined=_declined(deps, approval, response.reason or ""),
        )
    if typed is None:
        return TurnResumption(parked=approval, still_pending=approval)
    _declined(deps, approval, "")
    denial: DeferredToolApprovalResult = ToolDenied(message=_DECLINED_BY_REPLY)
    return TurnResumption(
        parked=approval,
        results=DeferredToolResults(approvals={approval.tool_call_id: denial}),
        user_prompt=typed,
    )


def turn_ends_before_the_run(
    resumption: TurnResumption,
    capture: _LeadRunCapture,
    writer: Any,
) -> bool:
    """Whether the answer leaves the Lead's run nothing to do.

    A declined proposal ends the turn as it stood. A sub-agent that stopped
    again leaves the Lead's run untouched, so the turn ends on the new call.
    """
    if resumption.declined is not None:
        _close_declined_card(resumption, capture, writer)
        return True
    if resumption.still_pending is None and resumption.still_durable is None:
        return False
    capture.pending_approval = resumption.still_pending
    capture.pending_durable_call = resumption.still_durable
    return True


def _close_declined_card(
    resumption: TurnResumption,
    capture: _LeadRunCapture,
    writer: Any,
) -> None:
    """Close the card as denied with no model call.

    The reply already on screen stays the turn's reply, so the turn leaves its
    answer and its questions as they stood.
    """
    if resumption.parked is None:
        return
    hint = approvals.deferred_hint(resumption.parked)
    for chunk in (
        ToolInputStartChunk(tool_call_id=hint.tool_call_id, tool_name=hint.tool_name),
        ToolInputAvailableChunk(
            tool_call_id=hint.tool_call_id,
            tool_name=hint.tool_name,
            input=hint.tool_args,
        ),
        ToolOutputDeniedChunk(tool_call_id=hint.tool_call_id),
    ):
        emit_chunk(writer, chunk)
    capture.parked_call_answered = True
    capture.proposal_declined = True


def _reparked(
    parked: PendingDurableCall,
    *,
    wait: SubAgentApprovalWait,
    user_message_id: UUID | None,
) -> TurnResumption:
    """Park the same dispatch again on the calls the resumed sub-agent reached."""
    fields = parked.model_dump(exclude={"durable_calls", "sub_agent"})
    if wait.durable:
        return TurnResumption(
            still_durable=PendingDurableCall(
                **fields,
                durable_calls=(
                    inner_durable_calls(wait.pending, wait.durable)
                    + outer_durable_calls(parked)
                ),
                sub_agent=wait.pending,
            ),
        )
    return TurnResumption(
        still_pending=PendingApproval(
            **fields,
            sub_agent=wait.pending,
            user_message_id=user_message_id,
        ),
    )


async def _resume_durable_call(
    *,
    state: PipelineState,
    deps: LeadDeps,
) -> TurnResumption | None:
    """Turn the workers' results into the results the Lead resumes with.

    A step that parked several durable calls resumes once, when the last task
    reports; an earlier arrival leaves the run waiting. Durable calls inside a
    sub-agent are answered inside that sub-agent first; its finished delta then
    becomes the Lead's deferred tool result, beside the answers to the calls
    the Lead made itself.
    """
    if not state.carries_durable_answer:
        return None
    parked = state.answered_durable_call
    if parked is None:
        return TurnResumption(still_durable=state.pending_durable_call)
    deps.state.turn_markers.record_control_tests(
        control_results_answered(parked, state.durable_answers),
    )
    answered = durable_tool_results(parked, state.durable_answers)
    sub_agent = parked.sub_agent
    if sub_agent is None:
        return TurnResumption(parked=parked, results=answered)
    inner, own = split_durable_answers(parked, answered)
    outcome: SubAgentOutcome | ModelRetry
    try:
        outcome = await resume_sub_agent(
            deps=deps,
            approval=parked,
            resume=SubAgentResume(
                messages=ModelMessagesTypeAdapter.validate_json(
                    sub_agent.messages_json
                ),
                results=inner,
            ),
        )
    except ModelRetry as retry:
        outcome = retry
    if isinstance(outcome, SubAgentApprovalWait):
        return _reparked(
            parked,
            wait=outcome,
            user_message_id=state.user_message_id,
        )
    return TurnResumption(
        parked=parked,
        results=DeferredToolResults(
            calls={**own.calls, parked.tool_call_id: outcome},
        ),
    )


def _resolve_own_approval(
    state: PipelineState,
    deps: LeadDeps,
    approval: PendingApproval,
) -> TurnResumption:
    """The answer to a call the Lead parked itself: a proposal card or another."""
    if approval.tool_name == PROPOSAL_TOOL:
        return _resolve_proposal(state, deps, approval)
    answers = answers_for(state, [approval.tool_call_id])
    if not answers:
        return TurnResumption(parked=approval)
    return TurnResumption(
        parked=approval,
        results=DeferredToolResults(approvals=answers),
    )


async def _resolve_pending_approval(
    *,
    state: PipelineState,
    deps: LeadDeps,
) -> TurnResumption:
    """Turn the user's approve/deny into the results the Lead resumes with.

    A sub-agent's approval is answered inside that sub-agent first; its
    finished delta then becomes the Lead's deferred tool result.
    """
    approval = state.pending_approval
    if approval is None:
        return TurnResumption()
    sub_agent = approval.sub_agent
    if sub_agent is None:
        return _resolve_own_approval(state, deps, approval)
    inner_ids = [call.tool_call_id for call in sub_agent.approvals]
    answers = answers_for(state, inner_ids)
    prompt: str | None = None
    if not answers:
        answers, prompt = unanswered_inner(state, approval, inner_ids)
    if not answers:
        # pydantic-ai re-executes a deferred call it is given no result for, so
        # a turn that resolves nothing keeps the card and runs no sub-agent.
        return TurnResumption(parked=approval, still_pending=approval)
    outcome: SubAgentOutcome | ModelRetry
    try:
        outcome = await resume_sub_agent(
            deps=deps,
            approval=approval,
            resume=SubAgentResume(
                messages=ModelMessagesTypeAdapter.validate_json(
                    sub_agent.messages_json
                ),
                results=DeferredToolResults(approvals=answers),
            ),
        )
    except ModelRetry as retry:
        # A dispatch refuses its own sub-agent's result here as it does on a
        # fresh call. pydantic-ai accepts a ModelRetry as a deferred call's
        # result, so the Lead reads the refusal and the turn does not end.
        outcome = retry
    if isinstance(outcome, SubAgentApprovalWait):
        # The typed reply is spent: it produced the denial this new approval
        # follows, so the next turn must not deliver it again.
        return TurnResumption(
            parked=approval,
            still_pending=approval.model_copy(
                update={
                    "sub_agent": outcome.pending,
                    "user_message_id": state.user_message_id,
                },
            ),
        )
    return TurnResumption(
        parked=approval,
        results=DeferredToolResults(
            approvals=sibling_answers(state, approval),
            calls={approval.tool_call_id: outcome},
        ),
        user_prompt=prompt,
    )


async def resolve_turn_resumption(
    *,
    state: PipelineState,
    deps: LeadDeps,
) -> TurnResumption:
    """What this turn re-enters: a worker's durable result, else a user's
    answer to an approval, else nothing."""
    durable = await _resume_durable_call(state=state, deps=deps)
    if durable is not None:
        return durable
    return await _resolve_pending_approval(state=state, deps=deps)
