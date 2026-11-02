"""The shape of one arc: how the turn's words read when a message names it, the
script each role plays, and how its words read for each combine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic_ai.messages import ModelMessage, ToolCallPart
from veupathdb_mcp.catalog import DecisionRequest, DecisionResponse, DecisionsTransport

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.intent import UserIntent

Role = Literal["lead", "frame", "verification", "execution"]

Script = Callable[[list[ModelMessage]], ToolCallPart]
Sequence = Callable[[list[ModelMessage]], list[ToolCallPart]]
Reading = Callable[[PipelineState, str], UserIntent]


async def no_operator_answer(request: DecisionRequest) -> DecisionResponse | None:
    del request
    return None


def history_free[T](build: Callable[[], T]) -> Callable[[list[ModelMessage]], T]:
    """A role step that reads nothing of the run, in the shape a role plays."""

    def play(_messages: list[ModelMessage]) -> T:
        return build()

    return play


@dataclass(frozen=True)
class Arc:
    """The intent the turn's words read as, one script per role, and the answer
    to each operator reading. A role the arc does not use plays its default, and
    an arc that names no operator answer answers no reading."""

    reading: Reading
    lead: Script
    frame: Script
    verification: Script
    execution: Script
    operators: DecisionsTransport = no_operator_answer

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
