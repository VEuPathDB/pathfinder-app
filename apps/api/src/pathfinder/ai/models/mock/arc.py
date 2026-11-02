"""The shape of one arc: how the turn's words read when a message names it, and
the script each role plays."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.intent import UserIntent

Role = Literal["lead", "frame", "verification", "execution"]

Script = Callable[[list[ModelMessage]], ToolCallPart]
Sequence = Callable[[list[ModelMessage]], list[ToolCallPart]]
Reading = Callable[[PipelineState, str], UserIntent]


def history_free[T](build: Callable[[], T]) -> Callable[[list[ModelMessage]], T]:
    """A role step that reads nothing of the run, in the shape a role plays."""

    def play(_messages: list[ModelMessage]) -> T:
        return build()

    return play


@dataclass(frozen=True)
class Arc:
    """The intent the turn's words read as, and one script per role. A role the
    arc does not use plays its default."""

    reading: Reading
    lead: Script
    frame: Script
    verification: Script
    execution: Script

    def script(self, role: Role) -> Script:
        match role:
            case "lead":
                return self.lead
            case "frame":
                return self.frame
            case "verification":
                return self.verification
            case "execution":
                return self.execution
