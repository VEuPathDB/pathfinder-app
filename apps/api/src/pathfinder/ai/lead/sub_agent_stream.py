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
from assistant_core.models.scripted import (
    current_scope_id,
    current_user_text,
)
from assistant_core.platform.logging import get_logger
from langgraph.config import get_stream_writer
from pydantic import BaseModel
from pydantic_ai import Agent, AgentRunResultEvent
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import (
    AgentStreamEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelMessagesTypeAdapter,
    PartStartEvent,
    RetryPromptPart,
)
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults
from pydantic_ai.usage import RunUsage

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
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
class _ToolRefusal:
    """One tool call the run sent back to the model, and the words it sent."""

    tool_name: str
    text: str


def _refusal_of(event: FunctionToolResultEvent) -> _ToolRefusal | None:
    """The refusal one tool result carries, or nothing when it succeeded.

    A validator's refusal arrives as error details rather than a sentence, so
    the messages are joined; the library's own retry instruction and its JSON
    dump stay out of what a reply quotes.
    """
    part = event.part
    if not isinstance(part, RetryPromptPart) or part.tool_name is None:
        return None
    content = part.content
    return _ToolRefusal(
        tool_name=part.tool_name,
        text=content
        if isinstance(content, str)
        else "; ".join(detail["msg"] for detail in content),
    )


def _exhausted_its_retries(
    exc: UnexpectedModelBehavior,
    refusal: _ToolRefusal | None,
) -> _ToolRefusal | None:
    """The refusal the library says ran out of retries, or nothing.

    The exception class also carries token limits, output-retry ceilings and
    streaming faults, so the raised message is the discriminator: it names the
    tool and the count the tool passed.
    """
    if refusal is None:
        return None
    if not exc.message.startswith(f"Tool {refusal.tool_name!r} exceeded max retries"):
        return None
    return refusal


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
    answered: frozenset[str] = (
        frozenset(resume.results.approvals) if resume is not None else frozenset()
    )
    output: OutputT | None = None
    wait: SubAgentApprovalWait | None = None
    refusal: _ToolRefusal | None = None
    usage = RunUsage()
    usage_recorded = False
    context_meter = ContextMeter(model_id=phase_model_id(deps.runtime, role))
    # A pass that continues a stopped one runs on its own budget, so its card
    # adds what the dispatch already spent.
    baseline = deps.sub_agent_usage_by_call.get(
        parent_tool_call_id, SubAgentCallUsage()
    )
    # The mock model reads these to pick a site-valid search and branch its
    # canned plan.
    current_scope_id.set(deps.runtime.site_id)
    current_user_text.set(deps.state.user_prompt)
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
                run.work_order if resume is None else None,
                deps=agent_deps,
                message_history=resume.messages if resume is not None else None,
                deferred_tool_results=resume.results if resume is not None else None,
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
                        refusal = _refusal_of(event) or refusal
                        _close_answered_approval(writer, event, answered)
                        emit_live_ledger(writer, deps, agent_deps)
                        emit_running_usage(
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
            record_stopped_usage(deps, role, parent_tool_call_id, usage)
            return None
        except UnexpectedModelBehavior as exc:
            exhausted = _exhausted_its_retries(exc, refusal)
            if exhausted is None:
                raise
            # One tool refused every attempt it was given. The refusal is the
            # pass's own account of the stop, and the draft holds what it bound.
            logger.warning(
                "sub-agent exhausted a tool's retries; keeping partial progress",
                role=role,
                tool=exhausted.tool_name,
                error=str(exc),
            )
            deps.last_phase_stop = _phase_stop(
                PhaseStopReason.TOOL_RETRIES,
                run=run,
                agent_deps=agent_deps,
                usage=usage,
                refusal=exhausted,
            )
            record_stopped_usage(deps, role, parent_tool_call_id, usage)
            return None
    if not usage_recorded:
        record_stopped_usage(deps, role, parent_tool_call_id, usage)
    return wait if wait is not None else output


def _phase_stop(
    reason: PhaseStopReason,
    *,
    run: PhaseRun,
    agent_deps: AgentDeps,
    usage: RunUsage,
    refusal: _ToolRefusal | None = None,
) -> PhaseStop:
    """The stop this run reports, sized by what it spent and what it bound."""
    draft = agent_deps.agent_state.operational_spec_draft
    return PhaseStop(
        role=run.role,
        reason=reason,
        tool_calls=usage.tool_calls,
        criteria_bound=sum(1 for c in draft.criteria if c.bound),
        criteria_declared=run.declared_criteria,
        tool_name="" if refusal is None else refusal.tool_name,
        refusal="" if refusal is None else refusal.text,
    )
