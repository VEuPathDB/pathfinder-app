"""A refused call is not run again with the same arguments until a call other than a read has run."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from assistant_core.capabilities.refused_calls import CallRefused
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_ai.toolsets.wrapper import WrapperToolset
from pydantic_core import to_jsonable_python

from pathfinder.ai.graph.turn_records import RefusedCall, TurnMarkers


class HoldsTurnMarkers(Protocol):
    """Deps that carry the record of the turn."""

    @property
    def turn_markers(self) -> TurnMarkers: ...


def _digest(tool_args: dict[str, Any]) -> str:
    text = json.dumps(to_jsonable_python(tool_args), sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass
class RefusalMemoryToolset[DepsT: HoldsTurnMarkers](WrapperToolset[DepsT]):
    """Holds each refusal until a call outside ``reads`` runs.

    The same call sent again fails with the refusal and does not run, and
    spends no retry. Sent a third time it is the refusal again, which the
    library counts against the tool's retries, so a loop ends the pass.
    """

    reads: frozenset[str] = frozenset()

    @property
    def id(self) -> str | None:
        return None

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[DepsT],
        tool: ToolsetTool[DepsT],
    ) -> Any:
        markers = ctx.deps.turn_markers
        arguments = _digest(tool_args)
        held = next(
            (
                r
                for r in markers.refused_calls
                if (r.tool_name, r.arguments) == (name, arguments)
            ),
            None,
        )
        if held is not None and not held.sent_again:
            held.sent_again = True
            msg = (
                f"{held.refusal} This call was refused before with these "
                "arguments, and only reads ran since, so it did not run again."
            )
            raise CallRefused(msg)
        if held is not None:
            raise ModelRetry(held.refusal)
        try:
            result = await self.wrapped.call_tool(name, tool_args, ctx, tool)
        except ModelRetry as refused:
            markers.refused_calls.append(
                RefusedCall(
                    tool_name=name, arguments=arguments, refusal=refused.message
                )
            )
            raise
        if name not in self.reads:
            markers.refused_calls.clear()
        return result
