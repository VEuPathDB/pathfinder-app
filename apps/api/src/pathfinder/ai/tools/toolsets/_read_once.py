"""A listed read answers each set of arguments once per run."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any

from pydantic_ai import RunContext, ToolFailed
from pydantic_ai.toolsets.abstract import AbstractToolset, ToolsetTool
from pydantic_ai.toolsets.wrapper import WrapperToolset
from pydantic_core import to_jsonable_python


def _arguments(tool_args: dict[str, Any]) -> str:
    return json.dumps(to_jsonable_python(tool_args), sort_keys=True)


@dataclass
class ReadOnceToolset[DepsT](WrapperToolset[DepsT]):
    """Holds the call that answered each listed read, for one run.

    The same read sent again fails without running and names that call, so it
    spends no retry and no site request. A read that failed is not held.
    """

    reads: frozenset[str] = frozenset()
    answered: dict[tuple[str, str], str] = field(default_factory=dict)

    @property
    def id(self) -> str | None:
        return None

    async def for_run(self, ctx: RunContext[DepsT]) -> AbstractToolset[DepsT]:
        wrapped = await self.wrapped.for_run(ctx)
        return replace(self, wrapped=wrapped, answered={})

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[DepsT],
        tool: ToolsetTool[DepsT],
    ) -> Any:
        if name not in self.reads:
            return await self.wrapped.call_tool(name, tool_args, ctx, tool)
        arguments = _arguments(tool_args)
        first = self.answered.get((name, arguments))
        if first is not None:
            msg = (
                f"{name} already answered these arguments in this run, in call "
                f"{first} ({arguments}). Read that answer; the same read does not "
                f"run again."
            )
            raise ToolFailed(msg)
        result = await self.wrapped.call_tool(name, tool_args, ctx, tool)
        self.answered[(name, arguments)] = ctx.tool_call_id or "an earlier call"
        return result
