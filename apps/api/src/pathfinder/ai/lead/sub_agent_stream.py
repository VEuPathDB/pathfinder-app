"""The sub-agent streaming engine.

Runs one phase agent, drives its inner events onto the chat stream, and parks
the run on a call the user or the worker must answer.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterable, AsyncIterator, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any

from assistant_core.capabilities.repetition_guard import RepetitionGuard
from assistant_core.graph.emit import emit_chunk
from assistant_core.graph.stream_events import turn_status_event
from assistant_core.graph.turn_state import (
    DurableDeferral,
    SubAgentApprovalCall,
    SubAgentApprovalPending,
)
from assistant_core.models.capture import maybe_wrap_model
from assistant_core.platform.logging import get_logger
from langgraph.config import get_stream_writer
from pydantic import BaseModel
from pydantic_ai import Agent, AgentRunResultEvent
from pydantic_ai.exceptions import (
    ModelAPIError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from pydantic_ai.messages import (
    AgentStreamEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelMessagesTypeAdapter,
    PartStartEvent,
)
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults
from pydantic_ai.usage import RunUsage

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.lead.sub_agent_events import (
    _announce_approval,
    _close_answered_approval,
    _forward_inner_event,
)
from pathfinder.ai.lead.sub_agent_progress import (
    ContextMeter,
    emit_live_ledger,
    emit_running_usage,
    record_stopped_usage,
    run_usage,
)
from pathfinder.ai.lead.sub_agent_stops import (
    GUARD_STOP_REASON,
    Stopping,
    ToolRefusal,
    early_stop,
    phase_stop,
    refusal_of,
    stopped,
)
from pathfinder.ai.lead.sub_agent_tools import (
    BUILD_SUB_AGENT_BY_ROLE,
    LeadDeps,
    SubAgentCallUsage,
    UnansweredStage,
    phase_model_id,
    phase_override_kwargs,
    phase_usage_limits,
)
from pathfinder.platform.model_keys import keyed_model

logger = get_logger(__name__)

_PHASE_STATUS_LABELS: dict[PhaseRole, str] = {
    "lead": "Thinking...",
    "frame": "Framing the strategy...",
    "execution": "Recovering failed steps...",
    "verification": "Verifying the strategy...",
}


@dataclass(frozen=True)
class PhaseRun:
    """What to run: which sub-agent, on what, at what size."""

    role: PhaseRole
    work_order: str
    declared_criteria: int = 0


@dataclass(frozen=True)
class SubAgentResume:
    """Re-entry into a sub-agent run that stopped at an approval."""

    messages: list[ModelMessage]
    results: DeferredToolResults


@dataclass(frozen=True)
class SubAgentApprovalWait:
    """A sub-agent run parked on the deferred calls of one model step.

    ``durable`` names the worker task answering each call, keyed by call id;
    empty when the calls are approvals the user answers.
    """

    pending: SubAgentApprovalPending
    durable: dict[str, DurableDeferral] = field(default_factory=dict)


def _park_run(
    *,
    writer: Any,
    role: PhaseRole,
    requests: DeferredToolRequests,
    messages: list[ModelMessage],
    deferrals: dict[str, DurableDeferral],
) -> SubAgentApprovalWait | None:
    """Park the run on the calls it stopped at.

    A durable call outranks an approval: its task is already running, so the
    worker's result must reach this run rather than a later one. One model
    step can hand several calls to the worker, and the run owes a result for
    each of them.
    """
    durable = [call for call in requests.calls if call.tool_call_id in deferrals]
    if durable:
        return SubAgentApprovalWait(
            pending=SubAgentApprovalPending(
                role=role,
                approvals=[
                    SubAgentApprovalCall(
                        tool_call_id=call.tool_call_id,
                        tool_name=call.tool_name,
                        args=call.args_as_dict(),
                    )
                    for call in durable
                ],
                messages_json=ModelMessagesTypeAdapter.dump_json(messages).decode(),
            ),
            durable={
                call.tool_call_id: deferrals[call.tool_call_id] for call in durable
            },
        )
    if not requests.approvals:
        return None
    return SubAgentApprovalWait(
        pending=SubAgentApprovalPending(
            role=role,
            approvals=[_announce_approval(writer, call) for call in requests.approvals],
            messages_json=ModelMessagesTypeAdapter.dump_json(messages).decode(),
        ),
    )


type _RunEvent = AgentStreamEvent | AgentRunResultEvent[Any]


@dataclass
class _PassAnswer:
    """Whether the model of one pass produced any part of an answer."""

    answered: bool = False

    async def watching(
        self,
        events: AsyncIterable[_RunEvent],
    ) -> AsyncIterator[_RunEvent]:
        """The same events, with a part the model started taken as an answer."""
        async for event in events:
            if isinstance(event, PartStartEvent):
                self.answered = True
            yield event


@contextlib.contextmanager
def _name_the_stage_that_did_not_answer(
    deps: LeadDeps,
    role: PhaseRole,
) -> Iterator[_PassAnswer]:
    """Record the stage of a pass that raises before its model answered.

    The turn's reply reads the record, so a researcher learns which stage to
    give another model.
    """
    deps.unanswered_stage = None
    answer = _PassAnswer()
    try:
        yield answer
    except Exception:
        if not answer.answered:
            deps.unanswered_stage = UnansweredStage(
                role=role,
                model_id=phase_model_id(deps.runtime, role),
            )
        raise


def _phase_agent(
    deps: LeadDeps,
    role: PhaseRole,
) -> tuple[Agent[AgentDeps, Any], AbstractContextManager[None]]:
    """The agent one dispatch runs, under the turn's override for its role."""
    agent = BUILD_SUB_AGENT_BY_ROLE[role]()
    overrides = phase_override_kwargs(deps.runtime, role)
    if "model" in overrides:
        overrides["model"] = maybe_wrap_model(keyed_model(overrides["model"]), role)
    if not overrides:
        return agent, contextlib.nullcontext()
    return agent, agent.override(**overrides)


def _absorb_result[OutputT: BaseModel](
    event: AgentRunResultEvent[Any],
    *,
    writer: Any,
    role: PhaseRole,
    expected_output_type: type[OutputT],
    deferrals: dict[str, DurableDeferral],
) -> tuple[OutputT | None, SubAgentApprovalWait | None]:
    """The typed delta this run produced, or the calls it parked."""
    agent_output = event.result.output
    if isinstance(agent_output, expected_output_type):
        return agent_output, None
    if isinstance(agent_output, DeferredToolRequests):
        return None, _park_run(
            writer=writer,
            role=role,
            requests=agent_output,
            messages=list(event.result.all_messages()),
            deferrals=deferrals,
        )
    return None, None


async def stream_sub_agent[OutputT: BaseModel](
    *,
    run: PhaseRun,
    agent_deps: AgentDeps,
    parent_tool_call_id: str,
    expected_output_type: type[OutputT],
    deps: LeadDeps,
    resume: SubAgentResume | None = None,
) -> OutputT | SubAgentApprovalWait | None:
    """Run a sub-agent, forward its inner events, and return the typed delta.

    Answers a ``resume`` into the run that produced it. Returns a
    ``SubAgentApprovalWait`` when the run stops on a call the user or the
    worker must answer, and ``None`` when the run stops early. An early stop is
    recorded on ``deps.last_phase_stop``, because a caller that reads only the
    partial draft cannot tell a stop from a pass that had nothing to bind.
    """
    role = run.role
    deps.last_phase_stop = None
    agent, override_ctx = _phase_agent(deps, role)
    writer = get_stream_writer()
    inner_calls: dict[str, str] = {}
    inputs = _RunInputs.of(run, resume)
    answered = inputs.answered
    output: OutputT | None = None
    wait: SubAgentApprovalWait | None = None
    refusal: ToolRefusal | None = None
    usage = RunUsage()
    usage_recorded = False
    stopping = Stopping(
        deps=deps,
        role=role,
        declared_criteria=run.declared_criteria,
        agent_deps=agent_deps,
        usage=usage,
        parent_tool_call_id=parent_tool_call_id,
    )
    context_meter = ContextMeter(model_id=phase_model_id(deps.runtime, role))
    # A pass that continues a stopped one runs on its own budget, so its card
    # adds what the dispatch already spent.
    baseline = deps.sub_agent_usage_by_call.get(
        parent_tool_call_id, SubAgentCallUsage()
    )
    bind_scripted_scope(deps.runtime.site_id, deps.state.user_prompt)
    emit_chunk(
        writer,
        turn_status_event(
            label=_PHASE_STATUS_LABELS.get(role, "Working..."),
            waiting_on_llm=True,
        ),
    )
    guard = agent_deps.tool_repetition_guard
    with override_ctx, _name_the_stage_that_did_not_answer(deps, role) as answer:
        try:
            async with agent.run_stream_events(
                inputs.prompt,
                deps=agent_deps,
                message_history=inputs.message_history,
                deferred_tool_results=inputs.deferred_tool_results,
                capabilities=[RepetitionGuard(guard=guard)],
                usage_limits=phase_usage_limits(run.declared_criteria),
                usage=usage,
            ) as events:
                async for event in answer.watching(events):
                    if isinstance(event, AgentRunResultEvent):
                        output, wait = _absorb_result(
                            event,
                            writer=writer,
                            role=role,
                            expected_output_type=expected_output_type,
                            deferrals=agent_deps.durable_deferrals,
                        )
                        deps.record_sub_agent_usage(
                            run_usage(event, deps, role, parent_tool_call_id),
                        )
                        usage_recorded = True
                        continue
                    _forward_inner_event(
                        parent_tool_call_id=parent_tool_call_id,
                        writer=writer,
                        inner_calls=inner_calls,
                        event=event,
                    )
                    if isinstance(event, FunctionToolResultEvent):
                        refusal = refusal_of(event) or refusal
                        if _after_tool_result(
                            event,
                            stopping,
                            writer=writer,
                            answered=answered,
                            context_meter=context_meter,
                            baseline=baseline,
                        ):
                            break
        except (UsageLimitExceeded, ModelAPIError, UnexpectedModelBehavior) as exc:
            stop = early_stop(exc, refusal)
            if stop is None:
                raise
            logger.warning(stop.event, role=role, **stop.fields)
            stopped(stop.reason, stopping, refusal=stop.refusal)
            return None
    if not usage_recorded:
        record_stopped_usage(deps, role, parent_tool_call_id, usage)
    return wait if wait is not None else output


@dataclass(frozen=True)
class _RunInputs:
    """What one run is started on: a fresh work order, or the parked run's
    messages with the answers it waited for."""

    prompt: str | None
    message_history: list[ModelMessage] | None
    deferred_tool_results: DeferredToolResults | None
    answered: frozenset[str]

    @classmethod
    def of(cls, run: PhaseRun, resume: SubAgentResume | None) -> _RunInputs:
        if resume is None:
            return cls(run.work_order, None, None, frozenset())
        return cls(
            None,
            resume.messages,
            resume.results,
            frozenset(resume.results.approvals),
        )


def _after_tool_result(
    event: FunctionToolResultEvent,
    stopping: Stopping,
    *,
    writer: Any,
    answered: frozenset[str],
    context_meter: ContextMeter,
    baseline: SubAgentCallUsage,
) -> bool:
    """Show the result's progress, and whether the guard ended the run on it.

    A guard stop keeps the draft as a budget stop does.
    """
    deps, agent_deps, role = stopping.deps, stopping.agent_deps, stopping.role
    _close_answered_approval(writer, event, answered)
    emit_live_ledger(writer, deps, agent_deps)
    emit_running_usage(
        writer,
        role,
        stopping.parent_tool_call_id,
        stopping.usage,
        context_meter,
        baseline=baseline,
    )
    guard = agent_deps.tool_repetition_guard
    stopped_by = guard.stopped_rule
    if stopped_by is None or event.tool_call_id != guard.stopped_call_id:
        return False
    logger.warning(
        "sub-agent stopped by the guard; keeping partial progress",
        role=role,
        rule=stopped_by,
        blocked=guard.total_blocked,
    )
    deps.last_phase_stop = phase_stop(
        GUARD_STOP_REASON[stopped_by], stopping, tool_name=event.part.tool_name or ""
    )
    return True
