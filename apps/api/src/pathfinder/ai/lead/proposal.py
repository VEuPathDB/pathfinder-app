"""An offer of further work that the Lead puts on a card, and the brief a yes
gives the edit."""

from __future__ import annotations

from typing import Annotated, Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Discriminator, Field

from pathfinder.ai.lead.card_reply import CardReply

PROPOSAL_TOOL = "propose_changes"
ADOPT_TOOL = "adopt_separating_strategy"
# The cards that offer work: a yes runs it, a no ends the turn as it stood.
OFFER_TOOLS: frozenset[str] = frozenset({PROPOSAL_TOOL, ADOPT_TOOL})


_SENTENCE = Field(
    min_length=1,
    max_length=300,
    description=(
        "The change as one plain sentence the researcher reads on the card, "
        "naming the search and the values it sets by their display names."
    ),
)
_CRITERION = Field(
    min_length=1,
    description="The criterion id the ledger lists for the step this changes.",
)
_VALUES = Field(
    min_length=1,
    description="Each parameter it sets, by name, to the wire value the site takes.",
)
_ANSWERS = (
    "The key of each requirement this change answers, copied from the key the "
    "Constraints section lists for it."
)


class SetValuesChange(CamelModel):
    """A change that sets parameter values on a criterion the strategy holds."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["set_values"] = "set_values"
    sentence: str = _SENTENCE
    criterion_id: str = _CRITERION
    params: dict[str, str] = _VALUES
    answers: list[str] = Field(default_factory=list, description=_ANSWERS)

    def binding(self) -> str:
        sets = ", ".join(f'{name} to "{value}"' for name, value in self.params.items())
        return f"on criterion {self.criterion_id}, set {sets}"


class AddCriterionChange(CamelModel):
    """A change that adds a criterion running one search of the site."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["add_criterion"] = "add_criterion"
    sentence: str = _SENTENCE
    search_name: str = Field(
        min_length=1, description="The site's name of the search the step runs."
    )
    params: dict[str, str] = Field(
        default_factory=dict,
        description="Each parameter the search takes a stated value for, by name.",
    )
    answers: list[str] = Field(default_factory=list, description=_ANSWERS)

    def binding(self) -> str:
        sets = "".join(f', {name} "{value}"' for name, value in self.params.items())
        return f"add a criterion running {self.search_name}{sets}"


ProposedChange = Annotated[
    SetValuesChange | AddCriterionChange,
    Discriminator("kind"),
]


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
    proposed_changes: list[ProposedChange] = Field(
        min_length=1,
        max_length=8,
        description=(
            "Each change a yes makes to the strategy, typed by what it binds: "
            "values set on a criterion, or a criterion added with its search. "
            "A removal is delete_step's card, which lists what it removes. A "
            "change that names no search and no value binds nothing and is "
            "refused."
        ),
    )
    left_to_ask: list[str] = Field(
        default_factory=list,
        description=(
            "The key of each requirement of this message that no change answers "
            "and the reply asks the researcher about, written as in a change's "
            "answers."
        ),
    )

    def named_keys(self) -> list[str]:
        """Each requirement key the card names, once, in the order it names them."""
        named = [k for c in self.proposed_changes for k in c.answers]
        return list(dict.fromkeys([*named, *self.left_to_ask]))

    def brief(self, note: str) -> str:
        """The edit's work order: the accepted changes and the researcher's note."""
        lines = [
            f"The researcher accepted this proposal: {self.question}",
            "Make these changes:",
            *(f"- {c.sentence} ({c.binding()})" for c in self.proposed_changes),
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
    "AddCriterionChange",
    "AdoptionArgs",
    "CardProposal",
    "DeclinedProposal",
    "Proposal",
    "ProposedChange",
    "SetValuesChange",
]
