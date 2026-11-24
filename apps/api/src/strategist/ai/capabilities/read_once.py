"""A read sent again with the same arguments runs once until any write of the turn."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, Self

from assistant_core.capabilities.refused_calls import CallRefused
from assistant_core.conversation.history import (
    compact_history,
    elide_consumed,
    is_elided,
)
from assistant_core.graph.tool_summary import summary_chunks
from pydantic_ai import RunContext
from pydantic_ai.capabilities.abstract import AbstractCapability, WrapToolExecuteHandler
from pydantic_ai.exceptions import ToolFailedError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolCallPart,
    ToolReturn,
    ToolReturnPart,
)
from pydantic_ai.tools import ToolDefinition
from pydantic_core import to_jsonable_python

from strategist.ai.agents.roles import StageRole
from strategist.ai.agents.tool_vocabulary import (
    CHECK_READS,
    READ_ONLY_TOOLS,
    RECORD_READS,
)
from strategist.ai.graph.turn_records import TurnMarkers


class HoldsTurnMarkers(Protocol):
    @property
    def turn_markers(self) -> TurnMarkers: ...


def _arguments(tool_args: dict[str, Any]) -> str:
    return json.dumps(to_jsonable_python(tool_args), sort_keys=True)


@dataclass(frozen=True)
class _Answer:
    call_id: str
    result: Any
    writes: int

    @property
    def text(self) -> str:
        match self.result:
            case ToolReturn(return_value=value):
                shown = value
            case _:
                shown = self.result
        return json.dumps(to_jsonable_python(shown, fallback=str))


def _shown(history: Sequence[ModelMessage], call_id: str) -> bool:
    """Whether the next request shows the answer of ``call_id`` whole.

    The history processors run again before that request, over a history that
    holds this response's calls too, so they decide what it shows.
    """
    messages = list(history)
    for process in (elide_consumed, compact_history):
        messages = process(messages)
    return any(
        type(part) is ToolReturnPart
        and part.tool_call_id == call_id
        and not is_elided(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
    )


def _refused(call: ToolCallPart, said: str) -> ToolFailedError:
    """The failed call the model reads, marked corrected as a refusal is."""
    refused = ToolFailedError(
        ToolReturnPart(
            tool_name=call.tool_name,
            content=said,
            tool_call_id=call.tool_call_id,
            tool_kind=call.tool_kind,
            outcome="failed",
            metadata=summary_chunks(call.tool_call_id, said, status="corrected"),
        )
    )
    refused.__cause__ = CallRefused(said)
    return refused


@dataclass
class ReadOnce[DepsT: HoldsTurnMarkers](AbstractCapability[DepsT]):
    """Holds the answer of each listed read for one run.

    A read in ``reads`` is held until the turn counts a write, by this agent or
    any other; one in ``lasting`` is held for the run. The same read sent again
    runs nothing and fails, so it spends no tool call of the budget and no site
    request: it names the call that answered while the model still sees that
    answer, and carries the answer again once the history elided it. Every call
    outside the listed reads counts one write. A read that failed is not held.
    """

    reads: frozenset[str] = frozenset()
    lasting: frozenset[str] = frozenset()
    answered: dict[tuple[str, str], _Answer] = field(default_factory=dict)

    @classmethod
    def of(cls, role: StageRole) -> Self:
        """The holds of one run of ``role``: every read until a write, and the
        reads no write of the run changes for the whole run."""
        lasting = CHECK_READS if role == "verification" else RECORD_READS
        return cls(reads=READ_ONLY_TOOLS, lasting=lasting)

    async def for_run(self, ctx: RunContext[DepsT]) -> ReadOnce[DepsT]:
        del ctx
        return replace(self, answered={})

    async def wrap_tool_execute(
        self,
        ctx: RunContext[DepsT],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
        handler: WrapToolExecuteHandler,
    ) -> Any:
        del tool_def
        markers = ctx.deps.turn_markers
        name = call.tool_name
        if name not in self.reads | self.lasting:
            try:
                return await handler(args)
            finally:
                markers.writes += 1
        key = (name, _arguments(args))
        first = self.answered.get(key)
        if first is not None and (
            name in self.lasting or first.writes == markers.writes
        ):
            said = (
                f"{name} answered these arguments in call {first.call_id} "
                f"({key[1]}), and nothing has changed since, so it did not run "
                "again and cost nothing."
            )
            again = (
                "Read that answer above."
                if _shown(ctx.messages, first.call_id)
                else f"That answer is no longer shown above; it is: {first.text}"
            )
            raise _refused(call, f"{said} {again}")
        writes = markers.writes
        result = await handler(args)
        self.answered[key] = _Answer(
            call_id=call.tool_call_id, result=result, writes=writes
        )
        return result


__all__ = ["HoldsTurnMarkers", "ReadOnce"]
