"""A read the site does not answer fails as one tool call, and the run goes on."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from functools import cache
from typing import Any

import httpx
from fastmcp.exceptions import ToolError
from pydantic import ValidationError
from pydantic_ai import ToolFailed
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import AgentDepsT, RunContext, ToolDefinition
from veupathdb.errors import DataParsingError, ExternalServiceError, WDKError
from veupathdb.jbrowse import JBrowseError
from veupathdb.wdk import WDKModel

from strategist.services.site_errors import site_status, site_words, unreached

# An account the request does not have is no outage; the error path reports it.
_IDENTITY_STATUSES = frozenset({401, 403})


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


def site_data_failure(tool_name: str, said: str) -> ToolFailed:
    return ToolFailed(
        f"{tool_name} read data the site served that it cannot use ({said}). "
        "Nothing was kept and the strategy is unchanged. Say that the site's data "
        "for this read could not be used, and answer from what the turn already "
        "holds."
    )


def site_reply_failure(tool_name: str, model: str) -> ToolFailed:
    return ToolFailed(
        f"{tool_name} got a reply from the site that did not parse ({model}). "
        "Nothing was read and the strategy is unchanged. Say that the site's reply "
        "to this read did not parse, and answer from what the turn already holds."
    )


@cache
def _reply_models() -> frozenset[str]:
    found: set[str] = set()
    pending: list[type[WDKModel]] = [WDKModel]
    while pending:
        model = pending.pop()
        found.add(model.__name__)
        pending.extend(model.__subclasses__())
    return frozenset(found)


def unparsed_site_reply(error: BaseException) -> str | None:
    """The reply model a site reply did not parse into, or None for any other error."""
    match error:
        case DataParsingError(__cause__=ValidationError() as cause):
            return unparsed_site_reply(cause)
        case ValidationError(title=title) if title in _reply_models():
            return title
        case _:
            return None


def _judged_read(tool_name: str, error: BaseException, said: str) -> ToolFailed:
    if unreached(error):
        return site_read_failure(tool_name, said)
    return site_refusal(tool_name, said)


def failed_read(tool_name: str, error: BaseException) -> ToolFailed:
    """The failed call for a site error: no answer at 500 or more, else a refusal."""
    return _judged_read(tool_name, error, site_words(error))


def _failed_tool(tool_name: str, error: ToolError) -> ToolFailed | None:
    cause = error.__cause__
    if site_status(cause) in _IDENTITY_STATUSES:
        return None
    if cause is None:
        return site_refusal(tool_name, str(error))
    return _judged_read(tool_name, cause, str(error))


def site_failure(error: BaseException) -> bool:
    """Whether the error is a site outage, timeout or refusal and no identity refusal."""
    match error:
        case (
            WDKError()
            | ExternalServiceError()
            | JBrowseError()
            | httpx.TransportError()
            | TimeoutError()
            | ConnectionError()
        ):
            return site_status(error) not in _IDENTITY_STATUSES
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
    """Fail a listed read that the site broke off or refused, and any call whose
    site reply did not parse, so it is not held as answered. Every other error
    propagates to the turn's error path or the refusal seam."""

    reads: frozenset[str] = frozenset()

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
        if (model := unparsed_site_reply(error)) is not None:
            raise site_reply_failure(tool_def.name, model) from error
        if tool_def.name not in self.reads:
            raise error
        match error:
            case ToolError():
                failed = _failed_tool(tool_def.name, error)
            case _ if site_failure(error):
                failed = failed_read(tool_def.name, error)
            case _:
                failed = None
        if failed is None:
            raise error
        raise failed from error
