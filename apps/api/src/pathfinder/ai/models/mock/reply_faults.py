"""The wrong calls of the faults the turn contract and the intent gate answer:
a reply silent about a gap or a caveat, a card that misstates a list size, an
open value asked in prose, and a classification that splits the organism."""

from __future__ import annotations

import re

from assistant_core.models.scripted import current_scope_id, scripted_call
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.arc import history_free
from pathfinder.ai.models.mock.fault_calls import (
    ANSWER,
    CONSULT,
    CallFault,
    WrongCall,
)
from pathfinder.ai.models.mock.findings import (
    caveat_paragraph,
    caveat_sentences,
    gap_paragraph,
    gap_sentences,
)
from pathfinder.ai.models.mock.reads import verification_prose
from pathfinder.ai.models.mock.separation_arc import run_reply
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.domain.evidence import RequirementCheck, VerificationReview

CLASSIFY = "classify_user_intent"
SEPARATE = "separate_controls"
# The requirement a check finds nothing in the strategy answers.
UNMET_REQUIREMENT = "annotated as essential"
# How many positives the misstated card reply leaves out of the list it names.
MISSTATED_BY = 2
# A binomial is two words; the words after it name the strain.
_BINOMIAL = 2
_SILENT_PROSE = "The check of the strategy is done."
_BLANK_LINES = re.compile(r"\n{3,}")


class _Prose(BaseModel):
    model_config = ConfigDict(extra="allow")

    prose: str


def _without(intended: ToolCallPart, parts: list[str]) -> ToolCallPart:
    """The arc's reply with each of ``parts`` taken out."""
    prose = _Prose.model_validate(intended.args_as_dict()).prose
    for part in parts:
        if part:
            prose = prose.replace(part, "")
    kept = _BLANK_LINES.sub("\n\n", prose).strip() or _SILENT_PROSE
    return scripted_call(ANSWER, {**intended.args_as_dict(), "prose": kept})


def unstated_caveat(messages: list[ModelMessage]) -> CallFault:
    """The arc's reply after a check that measured a caveat, with every count
    of the check left out."""
    measured = bool(caveat_sentences(messages))
    left_out = [caveat_paragraph(messages), verification_prose(messages)]

    def fault(intended: ToolCallPart) -> ToolCallPart | None:
        if not measured or intended.tool_name != ANSWER:
            return None
        return _without(intended, left_out)

    return fault


def unstated_gap(messages: list[ModelMessage]) -> CallFault:
    """The arc's reply after a check that found a gap, with the gaps left out."""
    found = bool(gap_sentences(messages))
    left_out = [gap_paragraph(messages)]

    def fault(intended: ToolCallPart) -> ToolCallPart | None:
        if not found or intended.tool_name != ANSWER:
            return None
        return _without(intended, left_out)

    return fault


class _DigestArgs(BaseModel):
    model_config = ConfigDict(extra="allow")

    review: VerificationReview = Field(default_factory=VerificationReview)


class _VerifyAnswer(BaseModel):
    model_config = ConfigDict(extra="allow")

    digest: _DigestArgs


def _unmet_requirement(intended: ToolCallPart) -> ToolCallPart | None:
    """VERIFY's answer with one more requirement row that nothing answers."""
    if intended.tool_name != ANSWER:
        return None
    answer = _VerifyAnswer.model_validate(intended.args_as_dict())
    review = answer.digest.review
    unmet = RequirementCheck(
        text=UNMET_REQUIREMENT,
        turn=1,
        answered_by=[],
        how="search",
        status="unmet",
        note="No step of the strategy reads it.",
    )
    rows = [*review.requirements, unmet]
    digest = answer.digest.model_copy(
        update={"review": review.model_copy(update={"requirements": rows})}
    )
    dumped = answer.model_copy(update={"digest": digest})
    return scripted_call(ANSWER, dumped.model_dump(by_alias=True, mode="json"))


class _Separation(BaseModel):
    model_config = ConfigDict(extra="allow")

    positive_controls: list[str]
    negative_controls: list[str] = Field(default_factory=list)


def _misstated_control_list(intended: ToolCallPart) -> ToolCallPart | None:
    """The arc's separation card, its reply naming fewer positives than the
    call carries."""
    if intended.tool_name != SEPARATE:
        return None
    lists = _Separation.model_validate(intended.args_as_dict())
    fewer = lists.positive_controls[:-MISSTATED_BY]
    reply = run_reply(fewer, lists.negative_controls)
    return scripted_call(SEPARATE, {**intended.args_as_dict(), "reply": reply})


def split_organism(organism: str) -> tuple[str, str] | None:
    """The binomial of a site organism and the strain words after it, or None
    for an organism with no strain words."""
    words = organism.split()
    if len(words) <= _BINOMIAL:
        return None
    return " ".join(words[:_BINOMIAL]), " ".join(words[_BINOMIAL:])


class _Classified(BaseModel):
    model_config = ConfigDict(extra="allow")

    intent: dict[str, object]


def _organism_split(intended: ToolCallPart) -> ToolCallPart | None:
    """The arc's classification with the site organism split: the binomial as
    the organism, and its strain as a requirement of its own."""
    split = split_organism(SiteValues.for_site(current_scope_id.get()).organism)
    if intended.tool_name != CLASSIFY or split is None:
        return None
    binomial, strain = split
    stated = [
        {
            "kind": "organism",
            "requestedValue": binomial,
            "label": "organism",
            "source": "user_explicit",
        },
        {
            "kind": "other",
            "requestedValue": f"{strain} genes",
            "label": "gene category",
            "source": "user_explicit",
        },
    ]
    classified = _Classified.model_validate(intended.args_as_dict())
    intent = {**classified.intent, "explicitConstraints": stated}
    return scripted_call(CLASSIFY, {"intent": intent})


class _Option(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str
    recommended: bool = False


class _Question(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt: str
    options: list[_Option] = Field(default_factory=list)

    def asked(self) -> str:
        chosen = [o.label for o in self.options if o.recommended]
        return f"{self.prompt} I recommend {chosen[0]}." if chosen else self.prompt


class _Card(BaseModel):
    model_config = ConfigDict(extra="ignore")

    questions: list[_Question]


def _open_value_in_prose(intended: ToolCallPart) -> ToolCallPart | None:
    """The arc's question card asked as a reply in prose instead."""
    if intended.tool_name != CONSULT:
        return None
    card = _Card.model_validate(intended.args_as_dict())
    return scripted_call(
        ANSWER,
        {
            "prose": " ".join(q.asked() for q in card.questions),
            "nextState": "await_user",
            "strategyChanged": False,
            "sources": [],
            "askedQuestions": [{"question": q.prompt} for q in card.questions],
        },
    )


unmet_requirement: WrongCall = history_free(lambda: _unmet_requirement)
misstated_control_list: WrongCall = history_free(lambda: _misstated_control_list)
organism_split: WrongCall = history_free(lambda: _organism_split)
open_value_in_prose: WrongCall = history_free(lambda: _open_value_in_prose)
