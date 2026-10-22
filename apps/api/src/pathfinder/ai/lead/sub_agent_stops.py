"""Why a sub-agent run ends before its result, and the typed stop it records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from assistant_core.capabilities.repetition_guard import BlockRule
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from pydantic_ai.messages import FunctionToolResultEvent, RetryPromptPart
from pydantic_ai.usage import RunUsage

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.agents.unserved import SearchNotServedError
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_progress import record_stopped_usage
from pathfinder.ai.lead.sub_agent_tools import LeadDeps

GUARD_STOP_REASON: dict[BlockRule, PhaseStopReason] = {
    "identical_arguments": PhaseStopReason.REPEATED_CALL,
    "call_cap": PhaseStopReason.CALL_CAP,
}


# A status below this is the request's own fault and is not sent again.
_SERVER_ERROR = 500


@dataclass(frozen=True)
class ToolRefusal:
    """One tool call the run sent back to the model, and the words it sent."""

    tool_name: str
    text: str


def refusal_of(event: FunctionToolResultEvent) -> ToolRefusal | None:
    """The refusal one tool result carries, or nothing when it succeeded.

    A validator's refusal arrives as error details rather than a sentence, so
    the messages are joined; the library's own retry instruction and its JSON
    dump stay out of what a reply quotes.
    """
    part = event.part
    if not isinstance(part, RetryPromptPart) or part.tool_name is None:
        return None
    content = part.content
    return ToolRefusal(
        tool_name=part.tool_name,
        text=content
        if isinstance(content, str)
        else "; ".join(detail["msg"] for detail in content),
    )


_OUTPUT_RETRIES_SPENT = "Exceeded maximum output retries ("


def spent_its_output_retries(exc: UnexpectedModelBehavior) -> bool:
    return exc.message.startswith(_OUTPUT_RETRIES_SPENT)


def exhausted_its_retries(
    exc: UnexpectedModelBehavior,
    refusal: ToolRefusal | None,
) -> ToolRefusal | None:
    """The refusal the library says ran out of retries, or nothing.

    The library raises this class itself for a spent tool or output budget, a
    token limit or a provider fault, with no field that names which, so the
    raised message is the discriminator: it names the tool the budget held.
    """
    if refusal is None:
        return None
    if not exc.message.startswith(f"Tool {refusal.tool_name!r} exceeded max retries"):
        return None
    return refusal


@dataclass(frozen=True)
class EarlyStop:
    """Why a run ended before its result, and the log line that says so."""

    reason: PhaseStopReason
    refusal: ToolRefusal | None
    event: str
    fields: dict[str, Any]


def early_stop(exc: Exception, refusal: ToolRefusal | None) -> EarlyStop | None:
    """The stop an exception of the run is, or None for an error to raise.

    The sub-agent writes each result into the shared draft as it goes, so every
    stop keeps the partial draft for the Lead to read. A usage ceiling is a
    budget, not a correctness failure. A request the provider did not complete
    is the request's failure, not the pass's. One tool that refused every
    attempt it was given, or an answer that failed every attempt, is the pass's
    own account of its stop.
    """
    match exc:
        case UsageLimitExceeded():
            return EarlyStop(
                PhaseStopReason.BUDGET,
                None,
                "sub-agent hit its usage ceiling; keeping partial progress",
                {"error": str(exc)},
            )
        case ModelAPIError() if the_provider_did_not_complete(exc):
            return EarlyStop(
                PhaseStopReason.PROVIDER,
                None,
                "sub-agent stopped on a provider error; keeping partial progress",
                {"error_type": type(exc).__name__},
            )
        case SearchNotServedError(message=message):
            return EarlyStop(
                PhaseStopReason.SEARCH_NOT_SERVED,
                ToolRefusal(tool_name="set_criterion", text=message),
                "sub-agent stopped on a search the site does not serve",
                {"error": message},
            )
        case UnexpectedModelBehavior():
            return _spent_retries(exc, refusal)
        case _:
            return None


def _spent_retries(
    exc: UnexpectedModelBehavior, refusal: ToolRefusal | None
) -> EarlyStop | None:
    if spent_its_output_retries(exc):
        return EarlyStop(
            PhaseStopReason.OUTPUT_RETRIES,
            None,
            "sub-agent exhausted its output retries; keeping partial progress",
            {"error": str(exc), "cause": str(exc.__cause__)},
        )
    exhausted = exhausted_its_retries(exc, refusal)
    if exhausted is None:
        return None
    return EarlyStop(
        PhaseStopReason.TOOL_RETRIES,
        exhausted,
        "sub-agent exhausted a tool's retries; keeping partial progress",
        {"tool": exhausted.tool_name, "error": str(exc)},
    )


@dataclass(frozen=True)
class Stopping:
    """What every early stop of one run records against."""

    deps: LeadDeps
    role: PhaseRole
    declared_criteria: int
    agent_deps: AgentDeps
    usage: RunUsage
    parent_tool_call_id: str


def stopped(
    reason: PhaseStopReason, stopping: Stopping, *, refusal: ToolRefusal | None = None
) -> None:
    """Record the stop as the run's typed result and the usage it spent."""
    deps = stopping.deps
    deps.last_phase_stop = phase_stop(reason, stopping, refusal=refusal)
    record_stopped_usage(
        deps, stopping.role, stopping.parent_tool_call_id, stopping.usage
    )


def the_provider_did_not_complete(error: ModelAPIError) -> bool:
    """Whether the provider failed the request rather than refusing it: no
    status, or a server status."""
    return not isinstance(error, ModelHTTPError) or error.status_code >= _SERVER_ERROR


def phase_stop(
    reason: PhaseStopReason,
    stopping: Stopping,
    *,
    refusal: ToolRefusal | None = None,
    tool_name: str = "",
) -> PhaseStop:
    """The stop this run reports, sized by what it spent and what it bound."""
    draft = stopping.agent_deps.agent_state.operational_spec_draft
    return PhaseStop(
        role=stopping.role,
        reason=reason,
        tool_calls=stopping.usage.tool_calls,
        criteria_bound=sum(1 for c in draft.criteria if c.bound),
        criteria_declared=stopping.declared_criteria,
        tool_name=tool_name if refusal is None else refusal.tool_name,
        refusal="" if refusal is None else refusal.text,
    )
