"""The sub-agent streaming engine.

Runs one phase agent, drives its inner events onto the chat stream, and parks
the run on a call the user or the worker must answer.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

from assistant_core.capabilities.repetition_guard import RepetitionGuard
from assistant_core.cost import cost_for_run
from assistant_core.graph.emit import emit_chunk
from assistant_core.graph.stream_events import (
    SubAgentCallPayload,
    sub_agent_call_event,
    turn_status_event,
)
from assistant_core.graph.turn_state import (
    DurableDeferral,
    SubAgentApprovalCall,
    SubAgentApprovalPending,
)
from assistant_core.models.capture import maybe_wrap_model
from assistant_core.models.scripted import (
    current_scope_id,
    current_user_text,
)
from assistant_core.platform.logging import get_logger
from langgraph.config import get_stream_writer
from pydantic import BaseModel
from pydantic_ai import AgentRunResultEvent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    FunctionToolResultEvent,
    ModelMessage,
    ModelMessagesTypeAdapter,
)
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults
from pydantic_ai.usage import RunUsage

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.stream_events import ledger_update_event
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_events import (
    _announce_approval,
    _close_answered_approval,
    _forward_inner_event,
)
from pathfinder.ai.lead.sub_agent_tools import (
    BUILD_SUB_AGENT_BY_ROLE,
    WIRE_PHASE_BY_ROLE,
    LeadDeps,
    SubAgentCallUsage,
    SubAgentRunUsage,
    apply_agent_state,
    phase_default_model_id,
    phase_override_kwargs,
    phase_usage_limits,
)
from pathfinder.ai.models.catalog import context_window_for

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
    agent = BUILD_SUB_AGENT_BY_ROLE[role]()
    writer = get_stream_writer()
    inner_calls: dict[str, str] = {}
    answered: frozenset[str] = (
        frozenset(resume.results.approvals) if resume is not None else frozenset()
    )
    output: OutputT | None = None
    wait: SubAgentApprovalWait | None = None
    usage = RunUsage()
    usage_recorded = False
    context_meter = _ContextMeter()
    # A pass that continues a stopped one runs on its own budget, so its card
    # adds what the dispatch already spent.
    baseline = deps.sub_agent_usage_by_call.get(
        parent_tool_call_id, SubAgentCallUsage()
    )
    # The mock model reads these to pick a site-valid search and branch its
    # canned plan.
    current_scope_id.set(deps.runtime.site_id)
    current_user_text.set(deps.state.user_prompt)
    override_kwargs = phase_override_kwargs(deps.runtime, role)
    if "model" in override_kwargs:
        override_kwargs["model"] = maybe_wrap_model(override_kwargs["model"], role)
    override_ctx = (
        agent.override(**override_kwargs)
        if override_kwargs
        else contextlib.nullcontext()
    )
    emit_chunk(
        writer,
        turn_status_event(
            label=_PHASE_STATUS_LABELS.get(role, "Working..."),
            waiting_on_llm=True,
        ),
    )
    guard = agent_deps.tool_repetition_guard
    with override_ctx:
        try:
            async with agent.run_stream_events(
                run.work_order if resume is None else None,
                deps=agent_deps,
                message_history=resume.messages if resume is not None else None,
                deferred_tool_results=resume.results if resume is not None else None,
                capabilities=[RepetitionGuard(guard=guard)],
                usage_limits=phase_usage_limits(run.declared_criteria),
                usage=usage,
            ) as events:
                async for event in events:
                    if isinstance(event, AgentRunResultEvent):
                        agent_output = event.result.output
                        if isinstance(agent_output, expected_output_type):
                            output = agent_output
                        elif isinstance(agent_output, DeferredToolRequests):
                            wait = _park_run(
                                writer=writer,
                                role=role,
                                requests=agent_output,
                                messages=list(event.result.all_messages()),
                                deferrals=agent_deps.durable_deferrals,
                            )
                        response = event.result.response
                        deps.record_sub_agent_usage(
                            SubAgentRunUsage(
                                usage=event.result.usage,
                                model_name=response.model_name,
                                provider_name=response.provider_name,
                                provider_url=response.provider_url,
                                parent_tool_call_id=parent_tool_call_id,
                            ),
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
                        _close_answered_approval(writer, event, answered)
                        _emit_live_ledger(writer, deps, agent_deps)
                        _emit_running_sub_agent_usage(
                            writer,
                            role,
                            parent_tool_call_id,
                            usage,
                            context_meter,
                            baseline=baseline,
                        )
                        if event.tool_call_id == guard.stopped_call_id:
                            # The guard refused the same call twice. The draft
                            # holds whatever the pass bound, as with a budget.
                            logger.warning(
                                "sub-agent repeated one call; keeping partial progress",
                                role=role,
                                blocked=guard.total_blocked,
                            )
                            deps.last_phase_stop = _phase_stop(
                                PhaseStopReason.REPEATED_CALL,
                                run=run,
                                agent_deps=agent_deps,
                                usage=usage,
                            )
                            break
        except UsageLimitExceeded as exc:
            # A usage ceiling is a budget, not a correctness failure. The
            # sub-agent writes each result into the shared draft as it goes,
            # so the Lead reads the partial draft.
            logger.warning(
                "sub-agent hit its usage ceiling; keeping partial progress",
                role=role,
                error=str(exc),
            )
            deps.last_phase_stop = _phase_stop(
                PhaseStopReason.BUDGET,
                run=run,
                agent_deps=agent_deps,
                usage=usage,
            )
            _record_stopped_usage(deps, role, parent_tool_call_id, usage)
            return None
    if not usage_recorded:
        _record_stopped_usage(deps, role, parent_tool_call_id, usage)
    return wait if wait is not None else output


def _phase_stop(
    reason: PhaseStopReason,
    *,
    run: PhaseRun,
    agent_deps: AgentDeps,
    usage: RunUsage,
) -> PhaseStop:
    """The stop this run reports, sized by what it spent and what it bound."""
    draft = agent_deps.agent_state.operational_spec_draft
    return PhaseStop(
        role=run.role,
        reason=reason,
        tool_calls=usage.tool_calls,
        criteria_bound=sum(1 for c in draft.criteria if c.bound),
        criteria_declared=run.declared_criteria,
    )


def _record_stopped_usage(
    deps: LeadDeps,
    role: PhaseRole,
    parent_tool_call_id: str,
    usage: RunUsage,
) -> None:
    """Record usage for a run that ended without a result event.

    A budget stop or a repetition stop yields no result, so the turn's
    totals would otherwise drop the run's tokens.
    """
    model_id = phase_default_model_id(role)
    provider, _, model = model_id.partition(":")
    deps.record_sub_agent_usage(
        SubAgentRunUsage(
            usage=usage,
            model_name=model or None,
            provider_name=provider or None,
            provider_url=None,
            parent_tool_call_id=parent_tool_call_id,
        ),
    )


@dataclass
class _ContextMeter:
    """The cumulative input tokens already reported for one dispatch.

    ``RunUsage.input_tokens`` accumulates over a run, so one request's input
    size is the delta between two readings. One request answers every one of
    its parallel tool calls, so an unchanged reading repeats the last size
    instead of reporting 0. A drop reads as 0.
    """

    seen_input: int = 0
    last_size: int = 0

    def last_request_input(self, usage: RunUsage) -> int:
        delta = usage.input_tokens - self.seen_input
        self.seen_input = usage.input_tokens
        if delta > 0:
            self.last_size = delta
        elif delta < 0:
            self.last_size = 0
        return self.last_size


def _emit_running_sub_agent_usage(
    writer: Any,
    role: PhaseRole,
    parent_tool_call_id: str,
    usage: RunUsage,
    meter: _ContextMeter,
    *,
    baseline: SubAgentCallUsage,
) -> None:
    """Push the dispatch's running tokens/cost and context fill after each
    inner tool call. ``baseline`` is what its earlier passes spent."""
    model_id = phase_default_model_id(role)
    provider, _, model = model_id.partition(":")
    cost = baseline.cost + cost_for_run(
        usage=usage,
        model_name=model or None,
        provider_name=provider or None,
        provider_url=None,
    )
    emit_chunk(
        writer,
        sub_agent_call_event(
            SubAgentCallPayload(
                tool_call_id=parent_tool_call_id,
                sub_agent=role,
                phase=WIRE_PHASE_BY_ROLE[role],
                state="started",
                model_id=model_id,
                tokens=baseline.tokens + usage.total_tokens,
                cost_usd=str(cost),
                context_tokens=meter.last_request_input(usage),
                context_window=context_window_for(model_id),
            )
        ),
    )


def _emit_live_ledger(
    writer: Any,
    deps: LeadDeps,
    agent_deps: AgentDeps,
) -> None:
    """Sync state and broadcast a ledger snapshot after a sub-agent tool call."""
    apply_agent_state(deps, agent_deps)
    ledger = derive_ledger(deps.state, deps.intent)
    emit_chunk(writer, ledger_update_event(ledger=ledger))
