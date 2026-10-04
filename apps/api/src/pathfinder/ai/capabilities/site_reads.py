"""A read the site does not answer fails as one tool call, and the run goes on."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic_ai import ToolFailed
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import AgentDepsT, RunContext, ToolDefinition
from veupathdb.errors import ExternalServiceError, WDKError

# An account the request does not have is no outage; the error path reports it.
_IDENTITY_STATUSES = frozenset({401, 403})
_SERVER_ERROR_STATUS = 500


def site_words(error: BaseException) -> str:
    """What the site said, with its status."""
    said = str(error).strip()
    match error:
        case WDKError(status=status) | ExternalServiceError(status=status):
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


def site_refusal(tool_name: str, said: str) -> ToolFailed:
    """The failed call the model reads in place of a read the site refused."""
    return ToolFailed(
        f"The site refused {tool_name} ({said}). Nothing was read and the strategy "
        "is unchanged. Correct the arguments the site names, or say that the site "
        "refused this read."
    )


def failed_read(tool_name: str, error: BaseException) -> ToolFailed:
    """The failed call for a site error: a refusal below 500, else no answer."""
    match error:
        case WDKError(status=status) | ExternalServiceError(status=status) if (
            status < _SERVER_ERROR_STATUS
        ):
            return site_refusal(tool_name, site_words(error))
        case _:
            return site_read_failure(tool_name, site_words(error))


def site_failure(error: BaseException) -> bool:
    """Whether the error is a site outage or timeout and no identity refusal."""
    match error:
        case WDKError(status=status) | ExternalServiceError(status=status):
            return status not in _IDENTITY_STATUSES
        case httpx.TransportError() | TimeoutError() | ConnectionError():
            return True
        case _:
            return False


async def read_in_time[T](
    tool_name: str, subject: str, read: Awaitable[T], *, deadline: float
) -> T:
    """The read's answer, or the failed call when the site breaks it off or
    does not answer within ``deadline`` seconds."""
    try:
        return await asyncio.wait_for(read, timeout=deadline)
    except TimeoutError as exc:
        said = f"no answer within {deadline} s for {subject}"
        raise site_read_failure(tool_name, said) from exc
    except (WDKError, ExternalServiceError, httpx.TransportError, OSError) as exc:
        if not site_failure(exc):
            raise
        raise failed_read(tool_name, exc) from exc


@dataclass
class SiteReadFailures(AbstractCapability[AgentDepsT]):
    """Fail a listed read that the site broke off or refused, so it is not held as answered.
    Every other error propagates to the turn's error path or the refusal seam."""

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
        if tool_def.name not in self.reads or not site_failure(error):
            raise error
        raise failed_read(tool_def.name, error) from error
