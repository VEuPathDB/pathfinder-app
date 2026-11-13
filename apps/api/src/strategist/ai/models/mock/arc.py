"""The shape of one arc: how the turn's words read when a message names it, the
script each role plays, and how its words read for each combine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from assistant_core.models.scripted import scripted_text
from pydantic_ai.messages import ModelMessage, TextPart, ToolCallPart
from veupathdb_mcp.catalog import DecisionRequest, DecisionResponse, DecisionsTransport

from strategist.ai.graph.state import PipelineState
from strategist.ai.lead.intent import UserIntent

Role = Literal["lead", "frame", "verification", "execution"]

Script = Callable[[list[ModelMessage]], ToolCallPart]
ExploreScript = Callable[[list[ModelMessage]], ToolCallPart | TextPart]
Sequence = Callable[[list[ModelMessage]], list[ToolCallPart]]
Reading = Callable[[PipelineState, str], UserIntent]

EXPLORE_ECHO = (
    "[mock] This answers in Explore mode and proposes no reading. Switch to "
    "Build and I will make it a strategy."
)


async def no_decision(request: DecisionRequest) -> DecisionResponse | None:
    del request
    return None


def explore_echo(messages: list[ModelMessage]) -> TextPart:
    del messages
    return scripted_text(EXPLORE_ECHO)


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
    operators: DecisionsTransport = no_decision
    explore: ExploreScript = explore_echo

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
