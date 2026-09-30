"""One eval case: the turns, what the assistant must do, where it came from.

A case is de-identified science. Its provenance names the site, the assistant,
how the case arrived and when, and never a user or a thread.
"""

from __future__ import annotations

import datetime
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import ReasoningEffort
from pydantic import ConfigDict, Field, model_validator

from pathfinder.evals.redaction import assert_redacted

CaseOrigin = Literal["promoted", "cataloged-failure", "uat-flow"]
# The card a turn ends on, as the researcher sees it: none, a question, an
# approval of a tool call, or an offer of further work.
GateEnd = Literal["none", "consult", "approval", "proposal"]
# How a case meets a card no answer names: "auto" says yes to every approval and
# offer and takes each question's recommended options; "stop" does the same but
# leaves the last turn's card unanswered; "decline-offers" says no to an offer,
# yes to any other approval and leaves a question unanswered; "leave" answers
# nothing. A card left unanswered is denied by the next message.
GatePolicy = Literal["auto", "stop", "decline-offers", "leave"]
# The tool a question card is raised by; every other card is an approval.
QUESTION_CARD = "consult_user"


class GateAnswer(CamelModel):
    """The answer to one card, named by the tool the card is for and the turn
    whose message raised it.

    A no may carry a comment. ``picks`` answers a question card: each question
    takes the options whose label holds a pick, else its recommended ones, and a
    free-text question takes the picks as its note.
    """

    model_config = ConfigDict(frozen=True)

    card: str = Field(min_length=1)
    turn: int = Field(ge=0)
    accept: bool = True
    comment: str | None = None
    picks: list[str] | None = None

    @model_validator(mode="after")
    def _one_kind_of_answer(self) -> GateAnswer:
        if self.accept and self.comment is not None:
            msg = "a comment is sent with a no only"
            raise ValueError(msg)
        if (self.picks is not None) != (self.card == QUESTION_CARD):
            msg = "a question card is answered by its picks, and only a question card"
            raise ValueError(msg)
        if self.picks is not None and not self.accept:
            msg = "a question card is answered by its picks, not by a no"
            raise ValueError(msg)
        return self


class GatePlan(CamelModel):
    """The answers a case names, and the policy for every card none names."""

    model_config = ConfigDict(frozen=True)

    policy: GatePolicy
    answers: list[GateAnswer] = Field(default_factory=list)

    def default_answer(
        self, card: str, *, turn: int, offer: bool, final: bool
    ) -> GateAnswer | None:
        """The policy's answer to a card no answer names, or None to leave it."""
        question = card == QUESTION_CARD
        match self.policy:
            case "leave":
                return None
            case "stop" if final:
                return None
            case "decline-offers" if question:
                return None
            case "decline-offers" if offer:
                return GateAnswer(card=card, turn=turn, accept=False)
            case _:
                return GateAnswer(card=card, turn=turn, picks=[] if question else None)


class CaseProvenance(CamelModel):
    """Where a case came from, as data. No field addresses a person.

    A promoted case names the staging id it was curated from; that id is
    random and the queue row behind it is gone. A cataloged failure names the
    knowledge-bundle item that recorded the bug, and a UAT case names its flow.
    """

    model_config = ConfigDict(frozen=True)

    site: str
    assistant: str
    origin: CaseOrigin
    added_at: str
    staging_id: str = ""
    reference: str = ""
    curator_note: str = ""

    @model_validator(mode="after")
    def _origin_names_its_source(self) -> CaseProvenance:
        if self.origin == "promoted" and not self.staging_id:
            msg = "a promoted case names the staging id it was curated from"
            raise ValueError(msg)
        if self.origin == "cataloged-failure":
            if not self.reference:
                msg = "a cataloged failure names the item that recorded it"
                raise ValueError(msg)
            if self.staging_id:
                msg = "a cataloged failure came from no staging row"
                raise ValueError(msg)
        if self.origin == "uat-flow":
            if not self.reference:
                msg = "a UAT case names the flow it was written from"
                raise ValueError(msg)
            if self.staging_id:
                msg = "a UAT case came from no staging row"
                raise ValueError(msg)
        return self


class RecordedCount(CamelModel):
    """The root count a flow recorded, the site build it held on, and the date read."""

    model_config = ConfigDict(frozen=True)

    count: int = Field(ge=0)
    build: str = Field(min_length=1)
    measured_on: datetime.date


class ExpectedOutcome(CamelModel):
    """What a run of the case must produce. An unset field is not compared.

    ``parameters`` names, per search, the values that search must carry. A
    parameter the case does not name is not compared. A null
    ``builds_strategy`` accepts a build and a turn that builds nothing.
    ``reply_names_its_searches`` holds a built strategy's reply to the title
    of every search step, and a turn that built nothing to a question.
    ``reply_gives_its_reasons`` holds it to the recorded term of each step that
    says why it runs its search, in the same paragraph as the step's title.
    ``root_operator`` is the root combine's operator, matched exactly, and
    ``final_count_below_every_input`` holds the root's count strictly below
    every search step's count. ``met_requirements`` and ``unmet_requirements``
    are the rows the check on the strategy reported with that status.
    ``counts_in_genes`` holds the reply to stating every count of the
    strategy's steps in genes, the unit the site counts it in, never as
    ``N transcripts``. ``root_count`` is judged for drift against the site's
    build, and ``ends_on`` is the gate the last turn stopped on.
    """

    model_config = ConfigDict(frozen=True)

    builds_strategy: bool | None
    structure: str | None = None
    record_type: str | None = None
    step_count: int | None = None
    verified: bool | None = None
    step_ids_unchanged: bool | None = None
    parameters: dict[str, dict[str, str]] = Field(default_factory=dict)
    reply_mentions: list[str] = Field(default_factory=list)
    reply_omits: list[str] = Field(default_factory=list)
    counts_in_genes: bool | None = None
    reply_names_its_searches: bool = False
    reply_gives_its_reasons: bool = False
    step_titles_omit: list[str] = Field(default_factory=list)
    root_operator: str | None = None
    final_count_below_every_input: bool | None = None
    met_requirements: int | None = None
    unmet_requirements: int | None = None
    unexpressed_requirements: int | None = None
    turn_reply_mentions: dict[int, list[str]] = Field(default_factory=dict)
    turn_reply_omits: dict[int, list[str]] = Field(default_factory=dict)
    assumed_stated: int | None = Field(default=None, ge=0)
    root_count: RecordedCount | None = None
    ends_on: GateEnd | None = None


class EvalCase(CamelModel):
    """The turns of one investigation, its expectation, and what it pins.

    The turns are driven in order on one thread, so a case can reach a state a
    first message cannot: an edit is a second message over a built strategy.
    ``effort`` is the effort the case was measured at, and ``attachments`` maps
    a turn's index to the files under the corpus ``files`` directory it sends.
    ``gates`` names the answer each card gets by its tool and turn, and the
    policy for every card no answer names. A case that must build nothing never
    accepts an offer.
    ``new_conversation_before`` names the turns that open a new conversation for
    the same researcher.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, pattern=r"^[a-z0-9-]+$")
    turns: list[str] = Field(min_length=1)
    site_id: str
    assistant_id: str
    rationale: str = Field(min_length=1)
    expected: ExpectedOutcome
    provenance: CaseProvenance
    effort: ReasoningEffort | None = None
    gates: GatePlan
    attachments: dict[int, list[str]] = Field(default_factory=dict)
    new_conversation_before: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _indexes_name_a_turn(self) -> EvalCase:
        for turn in self.attachments:
            if not 0 <= turn < len(self.turns):
                msg = f"an attachment names turn {turn}, and the case has {len(self.turns)}"
                raise ValueError(msg)
        for turn in self.new_conversation_before:
            if not 0 < turn < len(self.turns):
                msg = f"a new conversation starts before a later turn, not turn {turn}"
                raise ValueError(msg)
        for answer in self.gates.answers:
            if answer.turn >= len(self.turns):
                msg = f"an answer names turn {answer.turn}, and the case has {len(self.turns)}"
                raise ValueError(msg)
        if self.expected.builds_strategy is False and (
            self.gates.policy == "auto"
            or (self.gates.policy == "stop" and len(self.turns) > 1)
        ):
            msg = "a case that must build nothing never accepts an offer"
            raise ValueError(msg)
        phrased = {*self.expected.turn_reply_mentions, *self.expected.turn_reply_omits}
        for turn in sorted(phrased):
            if not 0 <= turn < len(self.turns):
                msg = f"a reply phrase names turn {turn}, and the case has {len(self.turns)}"
                raise ValueError(msg)
        return self

    def _free_text(self) -> list[str]:
        """Every text the case carries that a person could have written."""
        expected = self.expected
        answers = self.gates.answers
        return [
            *self.turns,
            self.rationale,
            self.provenance.curator_note,
            *expected.reply_mentions,
            *expected.reply_omits,
            *expected.step_titles_omit,
            *(p for phrases in expected.turn_reply_mentions.values() for p in phrases),
            *(p for phrases in expected.turn_reply_omits.values() for p in phrases),
            *(v for values in expected.parameters.values() for v in values.values()),
            *(name for names in self.attachments.values() for name in names),
            *(answer.comment for answer in answers if answer.comment is not None),
            *(pick for answer in answers for pick in answer.picks or []),
        ]

    def assert_de_identified(self) -> bool:
        """True when no text field carries an identity pattern."""
        for text in self._free_text():
            assert_redacted(text)
        return True


__all__ = [
    "QUESTION_CARD",
    "CaseOrigin",
    "CaseProvenance",
    "EvalCase",
    "ExpectedOutcome",
    "GateAnswer",
    "GateEnd",
    "GatePlan",
    "GatePolicy",
    "RecordedCount",
]
