"""The faults the turn contract and the intent's hold answer: an open value
asked in prose, and a reading that splits the organism."""

from __future__ import annotations

from assistant_core.models.scripted import scripted_call
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.messages import ToolCallPart

from strategist.ai.lead.intent import UserIntent
from strategist.ai.models.mock.arc import history_free
from strategist.ai.models.mock.arc_readings import stated
from strategist.ai.models.mock.fault_calls import (
    ANSWER,
    CONSULT,
    WrongCall,
)
from strategist.ai.models.mock.site_values import SiteValues

# A binomial is two words; the words after it name the strain.
_BINOMIAL = 2


def split_organism(organism: str) -> tuple[str, str] | None:
    """The binomial of a site organism and the strain words after it, or None
    for an organism with no strain words."""
    words = organism.split()
    if len(words) <= _BINOMIAL:
        return None
    return " ".join(words[:_BINOMIAL]), " ".join(words[_BINOMIAL:])


def organism_split(intent: UserIntent, site_id: str) -> UserIntent:
    """The arc's reading with the site organism split: the binomial as the
    organism, and its strain as a requirement of its own."""
    split = split_organism(SiteValues.for_site(site_id).organism)
    if split is None:
        return intent
    binomial, strain = split
    return UserIntent.model_validate(
        {
            **intent.model_dump(by_alias=True),
            "explicitConstraints": [
                stated(
                    "organism",
                    "organism",
                    binomial,
                    typed={"kind": "organism", "organism": binomial},
                ),
                stated(
                    "untyped",
                    "gene category",
                    f"{strain} genes",
                    typed={"kind": "untyped", "text": f"{strain} genes"},
                ),
            ],
        }
    )


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
            "askedQuestions": [{"question": q.prompt} for q in card.questions],
        },
    )


open_value_in_prose: WrongCall = history_free(lambda: _open_value_in_prose)
