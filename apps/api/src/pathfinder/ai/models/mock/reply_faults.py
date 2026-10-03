"""The wrong calls of the faults the turn contract and the intent gate answer:
a reply that writes a count outside a reference, an open value asked in prose,
and a classification that splits the organism."""

from __future__ import annotations

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
from pathfinder.ai.models.mock.reads import unshown_count_sentence
from pathfinder.ai.models.mock.site_values import SiteValues

CLASSIFY = "classify_user_intent"
# A binomial is two words; the words after it name the strain.
_BINOMIAL = 2


class _Prose(BaseModel):
    model_config = ConfigDict(extra="allow")

    prose: str


def unshown_count(messages: list[ModelMessage]) -> CallFault:
    """The arc's reply with a count written in it outside a reference."""
    count = unshown_count_sentence(messages)

    def fault(intended: ToolCallPart) -> ToolCallPart | None:
        if intended.tool_name != ANSWER:
            return None
        prose = _Prose.model_validate(intended.args_as_dict()).prose
        return scripted_call(
            ANSWER, {**intended.args_as_dict(), "prose": f"{prose} {count}"}
        )

    return fault


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
            "askedQuestions": [{"question": q.prompt} for q in card.questions],
        },
    )


organism_split: WrongCall = history_free(lambda: _organism_split)
open_value_in_prose: WrongCall = history_free(lambda: _open_value_in_prose)
