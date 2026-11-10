from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from uuid import uuid4

from assistant_core.capabilities.repetition_guard import RepetitionGuard
from assistant_core.conversation.vercel_adapter import PhaseStreamEmitter
from assistant_core.graph.emit import emit_chunk, emit_turn_usage
from assistant_core.graph.stream_events import turn_status_event
from assistant_core.graph.turn_state import (
    PendingApproval,
    PendingDurableCall,
)
from assistant_core.memory.schemas import MemoryValue
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime
from langgraph.types import Command
from pydantic_ai import AgentRunResultEvent
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import AgentStreamEvent
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.ui.vercel_ai.response_types import (
    BaseChunk,
    ErrorChunk,
    TextDeltaChunk,
    TextEndChunk,
    TextStartChunk,
)
from pydantic_ai.usage import RunUsage

from pathfinder.ai.capabilities.metering import SpendMeter, charge_spend
from pathfinder.ai.explore.explore_agent import ExploreAgent, build_explore_agent
from pathfinder.ai.explore.explore_model import resolve_explore_model_context
from pathfinder.ai.explore.readings_card import proposal_counts, proposals
from pathfinder.ai.graph._explore_turn import (
    ExploreTurn,
    explore_exchange,
    explore_park,
    explore_state_delta,
    explore_turn_for,
    hand_over_reading,
    hands_over,
)
from pathfinder.ai.graph._lead_capture import LeadRunCapture, emit_lead_usage
from pathfinder.ai.graph._lead_card_hold import CardHold
from pathfinder.ai.graph._lead_durable import (
    control_results_answered,
    statistics_answered,
)
from pathfinder.ai.graph._lead_facts import show_the_links
from pathfinder.ai.graph._lead_model import LeadModelContext
from pathfinder.ai.graph._lead_reading import classify_the_words
from pathfinder.ai.graph._lead_stops import (
    fallback_prose,
    guard_stop_of,
    loop_stop_prose,
    noting_a_provider_failure,
    run_stop_reply,
    strategy_change,
)
from pathfinder.ai.graph._lead_turn import memory_index, retrieve_memories
from pathfinder.ai.graph.rebuild import rebuilt_state
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.graph.stream_events import (
    BuildOfferPayload,
    build_offer_event,
    facts_event,
    recalled_memories_event,
    turn_route_event,
)
from pathfinder.ai.lead.lead_memory_tools import ask_about_the_preferences
from pathfinder.ai.lead.linked_pages import read_linked_pages
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_budget import lead_token_budget, lead_usage_limits
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.reply_note import render_note
from pathfinder.domain.strategy.reading_plan import OfferedReading
from pathfinder.platform.tiers import EXPLORE_ROLE

_FINALIZE: Literal["finalize_turn"] = "finalize_turn"

type _RunEvent = AgentStreamEvent | AgentRunResultEvent[str | DeferredToolRequests]


class ExploreNode(Protocol):
    def __call__(
        self,
        state: PipelineState,
        *,
        runtime: Runtime[Context],
    ) -> Awaitable[Command[Literal["finalize_turn"]]]: ...


@dataclass
class _ExploreRun:
    output: str | DeferredToolRequests | None = None
    parked: PendingApproval | PendingDurableCall | None = None
    stop: str = ""
    capture: LeadRunCapture = field(default_factory=LeadRunCapture)


async def _recalled(
    state: PipelineState, runtime: Runtime[Context], writer: Any
) -> list[MemoryValue]:
    stored, index = await asyncio.gather(
        retrieve_memories(state, runtime), memory_index(state, runtime)
    )
    state.domain.memory_index = index
    fresh = state.domain.memories_to_show(stored)
    if fresh:
        emit_chunk(writer, recalled_memories_event(memories=fresh))
    return [s.value for s in stored]


def _absorb(
    event: AgentRunResultEvent[str | DeferredToolRequests],
    deps: LeadDeps,
    run: _ExploreRun,
    writer: Any,
) -> None:
    output = event.result.output
    run.output = output
    if isinstance(output, DeferredToolRequests):
        ask_about_the_preferences(output, writer)
        run.parked = explore_park(output, deps, list(event.result.all_messages()))


@dataclass(frozen=True, kw_only=True)
class _Stream:
    agent: ExploreAgent
    deps: LeadDeps
    turn: ExploreTurn
    model: LeadModelContext
    meter: SpendMeter


async def _stream(stream: _Stream, run: _ExploreRun, writer: Any) -> CardHold:
    deps, turn = stream.deps, stream.turn
    guard = deps.tool_repetition_guard
    hold = CardHold(resumed={hint.tool_call_id for hint in turn.hints})
    emitter = PhaseStreamEmitter(
        message_id=str(uuid4()),
        deferred_hints=list(turn.hints),
        prompt_message_id=turn.prompt_message_id,
    )

    usage = RunUsage()
    limits = lead_usage_limits()

    async def _events() -> AsyncGenerator[_RunEvent]:
        try:
            async with stream.agent.run_stream_events(
                turn.prompt,
                deps=deps,
                message_history=turn.history,
                deferred_tool_results=turn.results,
                capabilities=[
                    RepetitionGuard(guard=guard),
                    lead_token_budget(),
                    stream.meter.on(stream.model.model_id),
                ],
                usage_limits=limits,
                usage=usage,
            ) as events:
                async for event in events:
                    run.capture.note_model_output(event)
                    if isinstance(event, AgentRunResultEvent):
                        _absorb(event, deps, run, writer)
                    yield event
                    guard_stop = guard_stop_of(event, guard)
                    if guard_stop is not None:
                        run.stop = loop_stop_prose(guard_stop)
                        return
        except (UsageLimitExceeded, UnexpectedModelBehavior) as exc:
            run.stop = run_stop_reply(exc, deps, usage, limits).prose

    with stream.model.override:
        async for chunk in emitter.chunks(
            noting_a_provider_failure(_events(), run.capture)
        ):
            if isinstance(chunk, ErrorChunk):
                run.capture.run_error = chunk.error_text
            for admitted in hold.admit(chunk):
                emit_chunk(writer, admitted)
    return hold


def _reply_of(state: PipelineState, run: _ExploreRun) -> str | None:
    if isinstance(run.output, str) and run.output:
        return run.output
    if run.parked is not None:
        return None
    return run.stop or fallback_prose(
        run.capture, None, change=strategy_change(state), own_stage=EXPLORE_ROLE
    )


def _text_chunks(text: str) -> list[BaseChunk]:
    text_id = f"explore-reply-{uuid4()}"
    return [
        TextStartChunk(id=text_id),
        TextDeltaChunk(id=text_id, delta=text),
        TextEndChunk(id=text_id),
    ]


def _show_the_reply(
    writer: Any, deps: LeadDeps, hold: CardHold, output: str | None
) -> str:
    if not hold.holds_a_card() and not output:
        return ""
    facts = turn_facts(deps)
    deps.state.domain.record_shown(facts.shown_records())
    if not facts.empty():
        emit_chunk(writer, facts_event(facts))
    show_the_links(writer, deps, facts)
    shown = [
        *(_text_chunks(render_note(output, facts)) if output else []),
        *hold.release(facts, deps.state.domain.open_questions),
    ]
    for chunk in shown:
        emit_chunk(writer, chunk)
    return " ".join(c.delta for c in shown if isinstance(c, TextDeltaChunk))


def _offer_the_build(
    writer: Any,
    parked: PendingApproval | PendingDurableCall | None,
    proposed: Sequence[OfferedReading],
) -> None:
    match proposed:
        case [reading] if parked is None:
            offer = BuildOfferPayload(
                label=reading.label,
                plan=reading.plan,
                gene_count=reading.gene_count,
                also=reading.also,
            )
            emit_chunk(writer, build_offer_event(offer))
        case _:
            return


async def _run_explore_turn(
    state: PipelineState, runtime: Runtime[Context]
) -> Command[Literal["finalize_turn"]]:
    writer = get_stream_writer()
    state = rebuilt_state(state)
    context = runtime.context
    turn = explore_turn_for(state)
    fresh = turn.answered is None
    if not fresh:
        emit_chunk(writer, turn_route_event("explore"))
    memories = (
        await _recalled(state, runtime, writer)
        if fresh
        else list(state.retrieved_memories)
    )
    deps = LeadDeps(
        state=state,
        intent=None,
        runtime=context,
        retrieved_memories=memories,
        linked_pages=await read_linked_pages(state.user_prompt),
    )
    if isinstance(turn.answered, PendingDurableCall):
        answers = state.durable_answers
        state.turn_markers.record_control_tests(
            control_results_answered(turn.answered, answers)
        )
        state.domain.record_statistics(statistics_answered(turn.answered, answers))
    if fresh:
        state.domain.record_request_text(state.user_prompt)
    agent = build_explore_agent()
    model = resolve_explore_model_context(
        agent,
        model_override=context.phase_models.get(EXPLORE_ROLE),
        reasoning_effort=context.phase_reasoning.get(EXPLORE_ROLE),
    )
    bind_scripted_scope(context.site_id, state.user_prompt)
    emit_chunk(
        writer,
        turn_status_event(
            label="Thinking...", waiting_on_llm=True, model=model.model_id
        ),
    )
    meter = SpendMeter()
    if fresh:
        await classify_the_words(state, deps, model_id=model.model_id, meter=meter)
    run = _ExploreRun()
    run.capture.lead_model = model.model_id
    run.capture.lead_reasoning_effort = model.reasoning_effort
    hold = await _stream(
        _Stream(agent=agent, deps=deps, turn=turn, model=model, meter=meter),
        run,
        writer,
    )
    reply = _show_the_reply(writer, deps, hold, _reply_of(state, run))
    _offer_the_build(writer, run.parked, proposals(deps))
    if run.parked is not None and hands_over(run.parked):
        hand_over_reading(state.domain, run.parked)
    state.domain.record_exchange(
        explore_exchange(
            state,
            reply=reply,
            parked=run.parked,
            answered=turn.answered,
            counts=proposal_counts(deps),
        )
    )
    await charge_spend(
        context.db_session_factory, user_id=state.user_id, spent=meter.spent
    )
    delta = explore_state_delta(
        state,
        deps,
        parked=run.parked,
        answered=turn.answered,
        spent=meter,
        memories=memories,
    )
    emit_turn_usage(
        writer, delta["turn_total_tokens"], str(delta["turn_total_cost_usd"])
    )
    emit_lead_usage(writer, run.capture, meter.tokens, str(meter.cost_usd))
    return Command(goto=_FINALIZE, update=delta)


def make_explore_node() -> ExploreNode:
    async def explore_node(
        state: PipelineState, *, runtime: Runtime[Context]
    ) -> Command[Literal["finalize_turn"]]:
        return await _run_explore_turn(state, runtime)

    return explore_node


__all__ = ["ExploreNode", "make_explore_node"]
