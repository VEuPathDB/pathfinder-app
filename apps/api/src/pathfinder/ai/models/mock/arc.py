"""The shape of one arc: the script each role plays when a message names it."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic_ai.messages import ModelMessage, ToolCallPart

Role = Literal["lead", "frame", "verification", "execution"]

Script = Callable[[list[ModelMessage]], ToolCallPart]
Sequence = Callable[[list[ModelMessage]], list[ToolCallPart]]


def history_free[T](build: Callable[[], T]) -> Callable[[list[ModelMessage]], T]:
    """A role step that reads nothing of the run, in the shape a role plays."""

    def play(_messages: list[ModelMessage]) -> T:
        return build()

    return play


@dataclass(frozen=True)
class Arc:
    """One script per role. A role the arc does not use plays its default."""

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
