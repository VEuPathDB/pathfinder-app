"""LangGraph node that runs the Lead Agent for a single chat turn.

The Lead is the only LLM in the dispatcher; sub-agents run as tools the
Lead invokes inside its single ``run_stream_events`` call. This module owns
the turn driver (``_drive_lead_stream``) and ``make_lead_node``, which binds
the driver to the hooks the graph was built with; run accounting lives in
``_lead_capture``, sub-agent event rendering in ``_lead_events``, model
selection in ``_lead_model``, and memory retrieval plus approval resolution in
``_lead_turn``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Sequence
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from assistant_core.capabilities.repetition_guard import (
    RepetitionGuard,
    ToolRepetitionGuard,
)
from assistant_core.conversation.vercel_adapter import (
    DeferredToolHint,
    PhaseStreamEmitter,
)
from assistant_core.cost import cost_for_run
from assistant_core.graph import approvals
from assistant_core.graph.emit import emit_chunk, emit_turn_usage
from assistant_core.graph.pre_turn import PreTurnHook
from assistant_core.graph.stream_events import turn_status_event
from assistant_core.graph.turn_agent import TurnAgentFactory
from assistant_core.graph.turn_state import ParkedCall, PendingDurableCall
from assistant_core.platform.logging import get_logger
from langgraph.config import get_stream_writer
from langgraph.errors import GraphBubbleUp
from langgraph.runtime import Runtime
from langgraph.types import Command
from pydantic_ai import AgentRunResultEvent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    AgentStreamEvent,
    FunctionToolResultEvent,
    UserContent,
)
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, ErrorChunk
from pydantic_ai.usage import RunUsage

from pathfinder.ai.graph._lead_capture import (
    _charge_token_delta,
    _emit_residual_prose,
    _LeadRunCapture,
    _persist_residual_quota,
    emit_lead_usage,
    usage_recorders,
)
from pathfinder.ai.graph._lead_card_hold import CardHold
from pathfinder.ai.graph._lead_delta import _build_state_delta
from pathfinder.ai.graph._lead_durable import (
    durable_resume_hints,
    pending_durable_call,
)
from pathfinder.ai.graph._lead_events import (
    handle_sub_agent_event,
    is_suppressed_sub_agent_chunk,
)
from pathfinder.ai.graph._lead_model import resolve_lead_model_context
from pathfinder.ai.graph._lead_stops import (
    absorb_loop_stop,
    final_reply,
    guard_stop_of,
    guard_stopped_on,
    stop_response,
)
from pathfinder.ai.graph._lead_turn import (
    TurnResumption,
    pending_approval,
    resolve_turn_resumption,
    retrieve_memories,
    turn_ends_before_the_run,
)
from pathfinder.ai.graph.rebuild import rebuilt_state
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.graph.stream_events import (
    ledger_update_event,
    recalled_memories_event,
)
from pathfinder.ai.graph.turn_status import (
    READING_THE_THREAD,
    RECALLING_AND_READING,
    turn_step_status,
)
from pathfinder.ai.lead.deleted_steps import ask_about_the_removals
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.lead_agent import LeadAgent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_budget import (
    budget_stop_report,
    lead_usage_limits,
    off_topic_budget_stop,
)
from pathfinder.ai.lead.turn_contract import LeadResponse

logger = get_logger(__name__)

_FINALIZE: Literal["finalize_turn"] = "finalize_turn"


class LeadNode(Protocol):
    """The call shape LangGraph invokes the turn node with."""

    def __call__(
        self,
        state: PipelineState,
        *,
        runtime: Runtime[Context],
    ) -> Awaitable[Command[Literal["finalize_turn"]]]: ...


def _run_prompt(
    state: PipelineState, resumption: TurnResumption
) -> str | Sequence[UserContent] | None:
    """The message the Lead's run starts from: the user's files and text.

    A turn that resumes a deferred tool carries the answer, not a new prompt,
    unless the user answered by sending a message instead of clicking.
    """
    if resumption.parked is not None and resumption.user_prompt is None:
        return None
    return state.user_content


def _absorb_run_result(
    event: AgentRunResultEvent[Any],
    capture: _LeadRunCapture,
    deps: LeadDeps,
) -> None:
    run_result = event.result
    capture.new_messages = list(run_result.new_messages())
    response = run_result.response
    if response.finish_reason:
        capture.finish_reason = response.finish_reason
    output = run_result.output
    if isinstance(output, LeadResponse):
        capture.response = output
    elif isinstance(output, DeferredToolRequests):
        messages = list(run_result.all_messages())
        capture.pending_durable_call = pending_durable_call(
            output=output,
            deps=deps,
            messages=messages,
        )
        if capture.pending_durable_call is None:
            capture.pending_approval = pending_approval(
                output=output,
                deps=deps,
                messages=messages,
            )
    usage = run_result.usage
    capture.tokens = usage.total_tokens
    capture.cost_usd = cost_for_run(
        usage=usage,
        model_name=response.model_name,
        provider_name=response.provider_name,
        provider_url=response.provider_url,
    )


async def _ask_about_what_it_parks(
    event: AgentRunResultEvent[Any], deps: LeadDeps, writer: Any
) -> None:
    """Name the step each parked removal acts on, before its card is drawn."""
    output = event.result.output
    if isinstance(output, DeferredToolRequests):
        await ask_about_the_removals(deps, output, writer)


def _emit_unless_suppressed(
    writer: Any,
    chunk: BaseChunk,
    sub_agent_tool_calls: dict[str, str],
    capture: _LeadRunCapture,
) -> None:
    """Write one chunk, unless a sub-agent already renders that call itself.

    The error chunk that ends a run is kept, so the turn's reply can name it.
    """
    if isinstance(chunk, ErrorChunk):
        capture.run_error = chunk.error_text
    if is_suppressed_sub_agent_chunk(chunk, sub_agent_tool_calls):
        return
    emit_chunk(writer, chunk)


def _emit_each(
    writer: Any,
    chunks: list[BaseChunk],
    sub_agent_tool_calls: dict[str, str],
    capture: _LeadRunCapture,
) -> None:
    for chunk in chunks:
        _emit_unless_suppressed(writer, chunk, sub_agent_tool_calls, capture)


def _stream_ends_after(
    event: AgentStreamEvent | AgentRunResultEvent[Any],
    guard: ToolRepetitionGuard,
    capture: _LeadRunCapture,
    usage: RunUsage,
    deps: LeadDeps,
) -> bool:
    """Whether this event is the last one the turn takes from the run."""
    if guard_stopped_on(event, guard) and isinstance(event, FunctionToolResultEvent):
        capture.guard_stop = guard_stop_of(event)
        return True
    return _off_topic_budget_ends_the_turn(capture, usage, deps)


def _off_topic_budget_ends_the_turn(
    capture: _LeadRunCapture,
    usage: RunUsage,
    deps: LeadDeps,
) -> bool:
    """Whether an out-of-scope turn has spent what such a turn may spend.

    A turn that already holds its answer is finished, so the budget takes
    nothing from it.
    """
    if capture.response is not None:
        return False
    stop = off_topic_budget_stop(usage, deps.intent)
    if stop is None:
        return False
    capture.response = stop_response(stop, changed=False)
    return True


def _resume_hints(parked: ParkedCall | None) -> list[DeferredToolHint]:
    """What the resumed stream needs to re-announce the calls it answers."""
    if parked is None:
        return []
    if isinstance(parked, PendingDurableCall):
        return durable_resume_hints(parked)
    return [approvals.deferred_hint(parked)]


async def _drive_lead_stream(
    *,
    state: PipelineState,
    agent: LeadAgent,
    deps: LeadDeps,
    capture: _LeadRunCapture,
    writer: Any,
    message_id: UUID,
) -> None:
    resumption = await resolve_turn_resumption(state=state, deps=deps)
    if turn_ends_before_the_run(resumption, capture, writer):
        return
    parked = resumption.parked
    hints = _resume_hints(parked)
    emitter = PhaseStreamEmitter(message_id=str(message_id), deferred_hints=hints)
    hold = CardHold(resumed={hint.tool_call_id for hint in hints})
    deferred_results = resumption.results
    capture.parked_call_answered = deferred_results is not None
    resume_prompt = _run_prompt(state, resumption)
    resume_messages = approvals.resume_history(parked) if parked is not None else None
    usage_acc = RunUsage()
    limits = lead_usage_limits()
    lead_model = resolve_lead_model_context(
        agent,
        model_override=deps.runtime.phase_models.get("lead"),
        reasoning_effort=deps.runtime.phase_reasoning.get("lead"),
    )
    agent_model = lead_model.model_id
    capture.lead_model = agent_model
    capture.lead_reasoning_effort = lead_model.reasoning_effort
    sub_agent_tool_calls: dict[str, str] = {}
    emit_chunk(
        writer,
        turn_status_event(label="Thinking...", waiting_on_llm=True, model=agent_model),
    )

    guard = deps.tool_repetition_guard

    async def _agent_events() -> AsyncGenerator[
        AgentStreamEvent | AgentRunResultEvent[Any]
    ]:
        # The budget stop is absorbed here, not around the emitter: the emitter
        # answers an exception of the run with an error chunk of its own. A
        # stream that ends instead leaves the turn its own reply.
        try:
            async with agent.run_stream_events(
                resume_prompt,
                deps=deps,
                message_history=resume_messages,
                deferred_tool_results=deferred_results,
                capabilities=[RepetitionGuard(guard=guard)],
                usage_limits=limits,
                usage=usage_acc,
            ) as events:
                async for event in events:
                    capture.note_model_output(event)
                    if isinstance(event, AgentRunResultEvent):
                        _absorb_run_result(event, capture, deps)
                        await _ask_about_what_it_parks(event, deps, writer)
                    else:
                        handle_sub_agent_event(
                            deps,
                            writer,
                            event,
                            sub_agent_tool_calls,
                            capture.sub_agent_usage_by_call,
                        )
                    await _charge_token_delta(
                        deps.runtime,
                        state,
                        capture,
                        usage_acc,
                        writer,
                        agent_model,
                    )
                    yield event
                    if _stream_ends_after(event, guard, capture, usage_acc, deps):
                        return
        except UsageLimitExceeded as exc:
            logger.warning(
                "lead reached its turn budget",
                conversation_id=str(state.conversation_id),
                error=str(exc),
            )
            capture.response = stop_response(
                budget_stop_report(
                    derive_ledger(deps.state, deps.intent),
                    deps.runtime.strategy_session,
                    deps.state.turn_markers,
                    deps.state.domain.open_questions,
                ),
                changed=deps.state.turn_markers.changed_strategy,
            )

    try:
        with lead_model.override:
            async for v6_chunk in emitter.chunks(_agent_events()):
                _emit_each(writer, hold.admit(v6_chunk), sub_agent_tool_calls, capture)
            _emit_each(writer, hold.release(), sub_agent_tool_calls, capture)
    # The emitter re-raises the graph's control-flow signal and answers every
    # other exception of the run with an error chunk, so these two handlers see
    # that signal and a failure of the loop that writes the chunks.
    except GraphBubbleUp:
        raise
    except Exception:
        logger.exception(
            "lead turn raised while emitting",
            conversation_id=str(state.conversation_id),
            user_id=str(state.user_id),
        )
        raise
    absorb_loop_stop(deps.state, capture, guard)


async def _run_lead_turn(
    state: PipelineState,
    runtime: Runtime[Context],
    *,
    pre_turn: PreTurnHook[PipelineState, Context],
    build_agent: TurnAgentFactory[LeadAgent],
) -> Command[Literal["finalize_turn"]]:
    writer = get_stream_writer()
    state = rebuilt_state(state)
    if state.resumes_parked_call:
        emit_chunk(writer, turn_step_status(READING_THE_THREAD))
        memories = list(state.retrieved_memories)
        working_state = await pre_turn(state, runtime.context)
    else:
        emit_chunk(writer, turn_step_status(RECALLING_AND_READING))
        stored, working_state = await asyncio.gather(
            retrieve_memories(state, runtime),
            pre_turn(state, runtime.context),
        )
        memories = [s.value for s in stored]
        if stored:
            emit_chunk(writer, recalled_memories_event(memories=stored))
    capture = _LeadRunCapture()
    message_id = uuid4()

    record_sub_agent_usage, record_tool_charge = usage_recorders(capture, state, writer)
    deps = LeadDeps(
        state=working_state,
        intent=state.domain.user_intent,
        runtime=runtime.context,
        retrieved_memories=memories,
        record_sub_agent_usage=record_sub_agent_usage,
        record_tool_charge=record_tool_charge,
        sub_agent_usage_by_call=capture.sub_agent_usage_by_call,
    )

    await _drive_lead_stream(
        state=state,
        agent=build_agent(),
        deps=deps,
        capture=capture,
        writer=writer,
        message_id=message_id,
    )

    capture.response = final_reply(
        capture,
        deps.unanswered_stage,
        changed=deps.state.turn_markers.changed_strategy,
    )

    _emit_residual_prose(writer, capture, message_id=message_id)
    residual_tokens, residual_cost = capture.residual_totals(state)
    await _persist_residual_quota(runtime.context, state, capture)
    emit_turn_usage(writer, residual_tokens, residual_cost)
    emit_lead_usage(writer, capture, capture.tokens, str(capture.cost_usd))
    final_ledger = derive_ledger(deps.state, deps.intent)
    emit_chunk(writer, ledger_update_event(ledger=final_ledger))
    delta = _build_state_delta(
        state=state,
        deps=deps,
        capture=capture,
        memories=memories,
    )
    return Command(goto=_FINALIZE, update=delta)


def make_lead_node(
    *,
    pre_turn: PreTurnHook[PipelineState, Context],
    build_agent: TurnAgentFactory[LeadAgent],
) -> LeadNode:
    """Bind the turn driver to the hooks the product wired at build time."""

    async def lead_node(
        state: PipelineState,
        runtime: Runtime[Context],
    ) -> Command[Literal["finalize_turn"]]:
        return await _run_lead_turn(
            state,
            runtime,
            pre_turn=pre_turn,
            build_agent=build_agent,
        )

    return lead_node
