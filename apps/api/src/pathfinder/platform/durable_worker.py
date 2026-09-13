"""The agent tools that defer to a worker, and what answers one where no worker
consumes its job."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, ParamSpec, TypeVar

from assistant_core.tasks.declaration import DurableTool
from assistant_core.tasks.decorator import durable_tool
from pydantic_ai.capabilities import WrapToolExecuteHandler
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import AgentDepsT, RunContext, ToolDefinition

P = ParamSpec("P")
R = TypeVar("R")

# The job name a declaration carries and the tool name the model calls are two
# names, so the second is recorded where the two are bound together.
_DEFERRING_TOOLS: dict[str, str] = {}

_worker_reachable: ContextVar[bool] = ContextVar(
    "durable_worker_reachable",
    default=True,
)


def durable_agent_tool(
    tool: DurableTool,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Defer this agent tool to the worker, under the name the model calls it by."""

    def decorate(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        _DEFERRING_TOOLS[fn.__name__] = tool.tool_name
        return durable_tool(tool)(fn)

    return decorate


def deferring_tool_names() -> Mapping[str, str]:
    """The job each deferring agent tool defers, by the name the model calls."""
    return MappingProxyType(_DEFERRING_TOOLS)


def durable_call_refusal(tool_name: str) -> str:
    """What the model reads in place of a durable call nothing can run."""
    return (
        f"{tool_name} runs on a worker this process cannot reach. Nothing "
        f"started. Say it was not available and report what you have."
    )


@contextmanager
def no_durable_worker() -> Iterator[None]:
    """Answer every durable call with a refusal inside this block."""
    token = _worker_reachable.set(False)
    try:
        yield
    finally:
        _worker_reachable.reset(token)


@dataclass
class DurableCallsRefused(AbstractCapability[AgentDepsT]):
    """Answer a durable call in writing where no worker consumes its job.

    A deferral that cannot happen leaves the run waiting for a result nothing
    produces, so the call is declined before it writes a task row.
    """

    async def wrap_tool_execute(
        self,
        ctx: RunContext[AgentDepsT],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
        handler: WrapToolExecuteHandler,
    ) -> Any:
        del ctx, call
        if _worker_reachable.get() or tool_def.name not in _DEFERRING_TOOLS:
            return await handler(args)
        return durable_call_refusal(tool_def.name)


__all__ = [
    "DurableCallsRefused",
    "deferring_tool_names",
    "durable_agent_tool",
    "durable_call_refusal",
    "no_durable_worker",
]
