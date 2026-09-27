"""Why a sub-agent dispatch ended without a delta."""

from __future__ import annotations

from enum import StrEnum

from assistant_core.graph.tool_summary import count_noun
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.domain.strategy.words import words_of


class PhaseStopReason(StrEnum):
    """What ended the run: its call budget, one call it kept repeating, one
    tool called past its own budget, or a tool that refused every attempt."""

    BUDGET = "budget"
    REPEATED_CALL = "repeated_call"
    CALL_CAP = "call_cap"
    TOOL_RETRIES = "tool_retries"


_REASON_PHRASE: dict[PhaseStopReason, str] = {
    PhaseStopReason.BUDGET: "stopped on its call budget",
    PhaseStopReason.REPEATED_CALL: "stopped after repeating one call",
    PhaseStopReason.CALL_CAP: "stopped past its call budget for {tool}",
    PhaseStopReason.TOOL_RETRIES: "stopped on a call one tool kept refusing",
}

_PASS_NAME: dict[PhaseRole, str] = {
    "lead": "lead",
    "frame": "framing",
    "execution": "recovery",
    "verification": "verification",
}


class PhaseStop(CamelModel):
    """The stop one dispatch reports: which pass, why, and its counts.

    A stop is a limit this turn imposed on itself, so the reply names it and
    never attributes it to VEuPathDB.
    """

    model_config = ConfigDict(frozen=True)

    role: PhaseRole
    reason: PhaseStopReason
    tool_calls: int = 0
    criteria_bound: int = 0
    criteria_declared: int = 0
    tool_name: str = ""
    refusal: str = ""

    def phrase(self) -> str:
        """Why the pass stopped, as the predicate of a sentence about it."""
        return _REASON_PHRASE[self.reason].format(tool=self.tool_name)

    def stated_by(self, prose: str) -> bool:
        """Whether the prose names the pass and says it stopped, in any case."""
        return {*words_of(_PASS_NAME[self.role]), "stopped"} <= set(words_of(prose))

    def render(self) -> str:
        """One sentence naming the stop, for the ledger and for a refusal."""
        sentence = (
            f"the {_PASS_NAME[self.role]} pass {self.phrase()} "
            f"after {count_noun(self.tool_calls, 'call')}"
        )
        if self.criteria_declared:
            sentence = (
                f"{sentence} with {self.criteria_bound} of "
                f"{self.criteria_declared} criteria bound"
            )
        if not self.refusal:
            return sentence
        return f"{sentence}; {self.tool_name} answered: {self.refusal}"
