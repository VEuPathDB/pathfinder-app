"""Turn-level helpers for the Lead node.

Memory retrieval at turn start, and what an answer - the user's click or the
worker's result - means for the run the turn parked. Reading the answer itself
belongs to ``_lead_answers``, the durable park and its partition to
``_lead_durable``, and the cycle's shared mechanics to the runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from assistant_core.graph import approvals
from assistant_core.graph.durable import durable_tool_results
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
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults

from pathfinder.ai.graph._lead_answers import (
    answers_for,
    sibling_answers,
    unanswered_inner,
)
from pathfinder.ai.graph._lead_durable import (
    enrichment_runs_answered,
    inner_durable_calls,
    outer_durable_calls,
    split_durable_answers,
)
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.dispatch_resume import SubAgentOutcome, resume_sub_agent
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
    wait on."""

    parked: ParkedCall | None = None
    results: DeferredToolResults | None = None
    still_pending: PendingApproval | None = None
    still_durable: PendingDurableCall | None = None
    user_prompt: str | None = None


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
    deps.state.turn_markers.record_enrichment_runs(
        enrichment_runs_answered(parked, state.durable_answers),
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
        answers = answers_for(state, [approval.tool_call_id])
        if not answers:
            return TurnResumption(parked=approval)
        return TurnResumption(
            parked=approval,
            results=DeferredToolResults(approvals=answers),
        )
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
