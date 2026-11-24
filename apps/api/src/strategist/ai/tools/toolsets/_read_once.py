"""A read sent again with the same arguments runs once while nothing changes."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from assistant_core.capabilities.refused_calls import CallRefused
from assistant_core.conversation.history import is_elided
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturn, ToolReturnPart
from pydantic_ai.toolsets.abstract import AbstractToolset, ToolsetTool
from pydantic_ai.toolsets.wrapper import WrapperToolset
from pydantic_core import to_jsonable_python


def _arguments(tool_args: dict[str, Any]) -> str:
    return json.dumps(to_jsonable_python(tool_args), sort_keys=True)


@dataclass(frozen=True)
class _Answer:
    call_id: str
    result: Any

    @property
    def text(self) -> str:
        match self.result:
            case ToolReturn(return_value=value):
                shown = value
            case _:
                shown = self.result
        return json.dumps(to_jsonable_python(shown, fallback=str))


def _shown(messages: Sequence[ModelMessage], call_id: str) -> bool:
    return any(
        type(part) is ToolReturnPart
        and part.tool_call_id == call_id
        and not is_elided(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
    )


@dataclass
class ReadOnceToolset[DepsT](WrapperToolset[DepsT]):
    """Holds the answer of each listed read, for one run.

    A read in ``reads`` is held until a call outside the listed reads runs; a
    read in ``lasting`` is held for the run. The same read sent again runs
    nothing and fails, so it spends no tool call of the run's budget and no
    site request. It names the call that answered while the model still sees
    that answer, and carries the answer again once the history elided it. A
    read that failed is not held.
    """

    reads: frozenset[str] = frozenset()
    lasting: frozenset[str] = frozenset()
    answered: dict[tuple[str, str], _Answer] = field(default_factory=dict)

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
        if name not in self.reads | self.lasting:
            result = await self.wrapped.call_tool(name, tool_args, ctx, tool)
            self.answered = {
                key: held
                for key, held in self.answered.items()
                if key[0] in self.lasting
            }
            return result
        arguments = _arguments(tool_args)
        first = self.answered.get((name, arguments))
        if first is not None:
            said = (
                f"{name} answered these arguments in call {first.call_id} "
                f"({arguments}), and nothing has changed since, so it did not run "
                "again and cost nothing."
            )
            again = (
                "Read that answer above."
                if _shown(ctx.messages, first.call_id)
                else f"That answer is no longer shown above; it is: {first.text}"
            )
            msg = f"{said} {again}"
            raise CallRefused(msg)
        result = await self.wrapped.call_tool(name, tool_args, ctx, tool)
        self.answered[(name, arguments)] = _Answer(
            call_id=ctx.tool_call_id or "an earlier call", result=result
        )
        return result
