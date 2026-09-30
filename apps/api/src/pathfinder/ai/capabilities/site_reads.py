"""A read the site does not answer fails as one tool call, and the run goes on."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from pydantic_ai import ToolFailed
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import AgentDepsT, RunContext, ToolDefinition
from veupathdb.errors import WDKError

# An account the request does not have is no outage; the error path reports it.
_IDENTITY_STATUSES = frozenset({401, 403})


def site_words(error: BaseException) -> str:
    """What the site said, with its status, and with the transport error named
    when it says nothing."""
    said = str(error).strip()
    cause = error.__cause__
    if cause is not None and not str(cause).strip():
        said = f"{said} {type(cause).__name__}".strip()
    match error:
        case WDKError(status=status):
            return f"HTTP {status}: {said}"
        case _:
            return said or type(error).__name__


def site_read_failure(tool_name: str, said: str) -> ToolFailed:
    """The failed call the model reads in place of a read the site broke off."""
    return ToolFailed(
        f"{tool_name} got no answer from the site ({said}). Nothing was read and "
        "the strategy is unchanged. Say that the site did not answer this read, "
        "and answer from what the turn already holds."
    )


def _site_failure(error: Exception) -> bool:
    """Whether the error is a site outage or timeout and no identity refusal."""
    match error:
        case WDKError(status=status):
            return status not in _IDENTITY_STATUSES
        case httpx.TransportError() | TimeoutError():
            return True
        case _:
            return False


@dataclass
class SiteReadFailures(AbstractCapability[AgentDepsT]):
    """Fail a listed read that the site broke off, so it is not held as answered.

    Every other error propagates: a write the site broke off belongs to the
    turn's error path, and a refusal this application names to the refusal seam.
    """

    reads: frozenset[str]

    async def on_tool_execute_error(
        self,
        ctx: RunContext[AgentDepsT],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
        error: Exception,
    ) -> Any:
        del ctx, call, args
        if tool_def.name not in self.reads or not _site_failure(error):
            raise error
        raise site_read_failure(tool_def.name, site_words(error)) from error
