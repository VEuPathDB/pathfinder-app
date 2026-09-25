"""An offer of further work that the Lead puts on a card, and the brief a yes
gives the edit."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field

from pathfinder.ai.lead.card_reply import CardReply

PROPOSAL_TOOL = "propose_changes"
ADOPT_TOOL = "adopt_separating_strategy"
# The cards that offer work: a yes runs it, a no ends the turn as it stood.
OFFER_TOOLS: frozenset[str] = frozenset({PROPOSAL_TOOL, ADOPT_TOOL})


class Proposal(CamelModel):
    """The work a card offers: one question and the changes a yes makes."""

    model_config = ConfigDict(frozen=True)

    question: str = Field(
        min_length=1,
        max_length=300,
        description=(
            "One sentence the researcher answers with yes or no, for example "
            '"Refine the strategy to require strict 3-hour specificity?"'
        ),
    )
    proposed_changes: list[str] = Field(
        min_length=1,
        max_length=8,
        description=(
            "Each change a yes makes to the strategy, as one plain sentence the "
            'edit realises: "Exclude genes highly expressed at the other '
            'post-blood-meal time points".'
        ),
    )

    def brief(self, note: str) -> str:
        """The edit's work order: the accepted changes and the researcher's note."""
        lines = [
            f"The researcher accepted this proposal: {self.question}",
            "Make these changes:",
            *(f"- {change}" for change in self.proposed_changes),
        ]
        if note:
            lines.append(f"The researcher's comment: {note}")
        return "\n".join(lines)


class CardProposal(Proposal):
    """A proposal as the card call carries it, with the reply above the card."""

    reply: CardReply


class AdoptionArgs(CamelModel):
    """The one argument an adoption card is called with."""

    model_config = ConfigDict(extra="ignore")

    task_id: str


class DeclinedProposal(Proposal):
    """A proposal the researcher answered no, with the note they sent."""

    note: str = ""


__all__ = [
    "ADOPT_TOOL",
    "OFFER_TOOLS",
    "PROPOSAL_TOOL",
    "AdoptionArgs",
    "CardProposal",
    "DeclinedProposal",
    "Proposal",
]
