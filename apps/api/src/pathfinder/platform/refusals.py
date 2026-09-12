"""The refusal seam every agent of this deployment carries, and its assembly."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic_ai.capabilities import AgentCapability
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import AgentDepsT, RunContext, ToolDefinition

from pathfinder.platform.errors import AppError

_NOT_FOUND_STATUS = 404
_SERVER_ERROR_STATUS = 500
# An account the request does not have is not an argument the model can change.
_IDENTITY_STATUSES = frozenset({401, 403})

# The tool that lists the ids each caller-supplied argument can hold.
LISTS_THE_IDS: Mapping[str, str] = {
    "control_set_id": "list_control_sets",
    "gene_set_id": "list_workbench_gene_sets",
}


class CallerSuppliedIds(BaseModel):
    """The ids a caller chose, as one tool call carries them."""

    model_config = ConfigDict(extra="ignore")

    control_set_id: str | None = None
    gene_set_id: str | None = None


def _unknown_id_guidance(args: dict[str, Any], stated: str) -> str:
    """The listing tool for each id the refusal names, and for no other id."""
    named = CallerSuppliedIds.model_validate(args).model_dump(exclude_none=True)
    return " ".join(
        f"{argument}={value!r} names nothing this account holds; "
        f"call {LISTS_THE_IDS[argument]} for the ids that exist."
        for argument, value in named.items()
        if value in stated
    )


def the_model_can_correct(error: AppError) -> bool:
    """Whether another call with other arguments can pass this refusal."""
    return (
        error.status < _SERVER_ERROR_STATUS and error.status not in _IDENTITY_STATUSES
    )


def refusal_retry_message(args: dict[str, Any], error: AppError) -> str:
    """What the model reads in place of the call that was refused."""
    stated = f"{error.code}: {error}"
    if error.status != _NOT_FOUND_STATUS:
        return stated
    guidance = _unknown_id_guidance(args, stated)
    return f"{stated} {guidance}" if guidance else stated


@dataclass
class ServiceRefusalRetry(AbstractCapability[AgentDepsT]):
    """Turn a correctable refusal raised inside a tool body into a retry.

    A refusal this application names, below 500 and not an identity refusal, is
    a call other arguments can pass, so the model answers it. Everything else
    propagates: an invariant failure, an outage and a sign-in all end the run
    where the error path reports them.
    """

    async def on_tool_execute_error(
        self,
        ctx: RunContext[AgentDepsT],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
        error: Exception,
    ) -> Any:
        del ctx, call, tool_def
        if not isinstance(error, AppError) or not the_model_can_correct(error):
            raise error
        raise ModelRetry(refusal_retry_message(args, error)) from error


def agent_capabilities(
    carried: Sequence[AgentCapability[AgentDepsT]],
) -> list[AgentCapability[AgentDepsT]]:
    """What one agent runs with, plus the seam every agent here carries.

    A refusal this application names answers the model on every assistant, so
    an agent that declares nothing else still answers one.
    """
    return [ServiceRefusalRetry[AgentDepsT](), *carried]


__all__ = [
    "LISTS_THE_IDS",
    "CallerSuppliedIds",
    "ServiceRefusalRetry",
    "agent_capabilities",
    "refusal_retry_message",
    "the_model_can_correct",
]
