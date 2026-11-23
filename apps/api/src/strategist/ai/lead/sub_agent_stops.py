"""Why a sub-agent run ends before its result, and the typed stop it records."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from assistant_core.capabilities.repetition_guard import BlockRule
from pydantic import ValidationError
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelHTTPError,
    ToolRetryError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from pydantic_ai.messages import FunctionToolResultEvent
from pydantic_ai.usage import RunUsage

from strategist.ai.agents.roles import PhaseRole
from strategist.ai.agents.unserved import SearchNotServedError
from strategist.ai.capabilities.error_classification import RETRY_DETAILS
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from strategist.ai.lead.sub_agent_tools import LeadDeps

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
    if part.outcome != "retried":
        return None
    return ToolRefusal(tool_name=part.tool_name, text=_said(part.content))


def _said(content: object) -> str:
    match content:
        case str() as said:
            return said
        case details:
            return "; ".join(
                ": ".join([*map(str, d.loc[-1:]), d.msg])
                for d in RETRY_DETAILS.validate_python(details)
            )


def answer_refusal(exc: UnexpectedModelBehavior) -> str:
    """What the last check of a spent answer said, or nothing."""
    match exc.__cause__:
        case ToolRetryError(tool_retry=retry):
            return _said(retry.content)
        case ValidationError() as invalid:
            return _said(invalid.errors())
        case _:
            return ""


_OUTPUT_RETRIES_SPENT = "Exceeded maximum output retries ("


def spent_its_output_retries(exc: UnexpectedModelBehavior) -> bool:
    return exc.message.startswith(_OUTPUT_RETRIES_SPENT)


_TOOL_RETRIES_SPENT = re.compile(
    r"^Tool '(?P<tool>.+)' exceeded max retries count of \d+"
)


def exhausted_its_retries(
    exc: UnexpectedModelBehavior, refusals: Mapping[str, ToolRefusal]
) -> ToolRefusal | None:
    """The refusal of the tool whose retries the library says ran out, or nothing.

    The library raises this class itself for a spent tool or output budget, a
    token limit or a provider fault, with no field that names which, so the
    raised message is the discriminator: it names the tool the budget held.
    """
    spent = _TOOL_RETRIES_SPENT.match(exc.message)
    if spent is None:
        return None
    tool = spent["tool"]
    return refusals.get(tool, ToolRefusal(tool_name=tool, text=""))


@dataclass(frozen=True)
class EarlyStop:
    """Why a run ended before its result, and the log line that says so."""

    reason: PhaseStopReason
    refusal: ToolRefusal | None
    event: str
    fields: dict[str, Any]


def early_stop(exc: Exception, refusals: Mapping[str, ToolRefusal]) -> EarlyStop | None:
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
            return _spent_retries(exc, refusals)
        case _:
            return None


def _spent_retries(
    exc: UnexpectedModelBehavior, refusals: Mapping[str, ToolRefusal]
) -> EarlyStop | None:
    if spent_its_output_retries(exc):
        return EarlyStop(
            PhaseStopReason.OUTPUT_RETRIES,
            None,
            "sub-agent exhausted its output retries; keeping partial progress",
            {"error": str(exc), "cause": str(exc.__cause__)},
        )
    exhausted = exhausted_its_retries(exc, refusals)
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
    """Record the stop as the run's typed result."""
    stopping.deps.last_phase_stop = phase_stop(reason, stopping, refusal=refusal)


def a_provider_call_failed(error: Exception) -> bool:
    return isinstance(error, (ModelAPIError, UnexpectedModelBehavior))


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
