from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from veupathdb.domain.parameters import VocabOption, nearest_entries
from veupathdb_mcp.catalog import (
    Choice,
    ChoiceQuestion,
    DecisionRequest,
    DecisionResponse,
    DecisionsTransport,
    PredicateQuestion,
    decide,
)

from pathfinder.ai.models.mock.arc import no_decision
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    OrganismValue,
)
from pathfinder.domain.strategy.organism_phrases import completed_entry
from pathfinder.domain.strategy.organism_picks import OrganismPick
from pathfinder.platform.config import get_settings
from pathfinder.platform.model_keys import is_mock_deployment

ORGANISM_QUESTION = "organism"
FIT_QUESTION = "fits"
NONE_FITS = "none_fits"
_PURPOSE = "organism entry"
_MAX_ENTRIES = 254
_OFFERED = 5
_CHOICE_TEXT = (
    "Which organism of the site do the researcher's words name? Choose "
    "none_fits when they name a group of organisms, a species the site holds "
    "several strains of without naming one, or an organism the site lacks."
)
_NONE_FITS_TEXT = (
    "The words name no one of these organisms: a genus or a group, a species "
    "of several strains with none named, or an organism the site does not hold."
)
_FIT_TEXT = (
    "The researcher's words name exactly the proposed organism: not a broader "
    "group, not a species whose strain they leave open, and not another organism."
)


@dataclass(frozen=True)
class NamedOrganisms:
    constraints: list[Constraint]
    picks: list[OrganismPick]


def _state(site_id: str, message: str, quote: str) -> str:
    return (
        f"VEuPathDB site: {site_id}.\n"
        f"The researcher's message: {message}\n"
        f'The words of the message that name the organism: "{quote}"'
    )


def _entries(vocabulary: Sequence[str], words: str) -> list[str]:
    if len(vocabulary) <= _MAX_ENTRIES:
        return list(vocabulary)
    options = [VocabOption(value=entry, display=entry) for entry in vocabulary]
    return nearest_entries(options, words, _MAX_ENTRIES)


def organism_request(
    site_id: str, message: str, quote: str, entries: Sequence[str]
) -> DecisionRequest:
    return DecisionRequest(
        input=_state(site_id, message, quote),
        questions=[
            ChoiceQuestion(
                name=ORGANISM_QUESTION,
                instructions=_CHOICE_TEXT,
                choices=[
                    *(
                        Choice(value=f"e{i}", description=entry)
                        for i, entry in enumerate(entries)
                    ),
                    Choice(value=NONE_FITS, description=_NONE_FITS_TEXT),
                ],
            )
        ],
    )


def fit_request(site_id: str, message: str, quote: str, entry: str) -> DecisionRequest:
    return DecisionRequest(
        input=f"{_state(site_id, message, quote)}\nProposed organism: {entry}",
        questions=[PredicateQuestion(name=FIT_QUESTION, instructions=_FIT_TEXT)],
    )


def _entry_of(choice: str, entries: Sequence[str]) -> str | None:
    if choice == NONE_FITS:
        return None
    return entries[int(choice.removeprefix("e"))]


async def _ask_the_service(request: DecisionRequest) -> DecisionResponse | None:
    return await decide(request, purpose=_PURPOSE)


@dataclass(frozen=True)
class _Reading:
    site_id: str
    message: str
    vocabulary: Sequence[str]
    ask: DecisionsTransport
    floor: float

    def offered(self, picked: str | None, words: str) -> list[str]:
        options = [VocabOption(value=entry, display=entry) for entry in self.vocabulary]
        near = nearest_entries(options, words, _OFFERED)
        first = [] if picked is None else [picked]
        return list(dict.fromkeys([*first, *near]))[:_OFFERED]

    async def pick(self, quote: str, words: str) -> OrganismPick:
        entries = _entries(self.vocabulary, words)
        chosen = await self.ask(
            organism_request(self.site_id, self.message, quote, entries)
        )
        answer = None if chosen is None else chosen.choice(ORGANISM_QUESTION)
        picked = None if answer is None else _entry_of(answer.choice, entries)
        if answer is None or picked is None:
            return OrganismPick(quote=quote, offered=self.offered(None, words))
        fit = await self.ask(fit_request(self.site_id, self.message, quote, picked))
        judged = None if fit is None else fit.predicate(FIT_QUESTION)
        return OrganismPick(
            quote=quote,
            picked=picked,
            confidence=0.0
            if judged is None
            else min(answer.confidence, judged.probability),
            offered=self.offered(picked, words),
        )

    def settled(self, pick: OrganismPick) -> str | None:
        return pick.picked if pick.confidence >= self.floor else None


def _named(c: Constraint, entry: str) -> Constraint:
    return c.model_copy(
        update={"requested_value": entry, "value": OrganismValue(organism=entry)}
    )


async def named_organisms(
    site_id: str,
    constraints: Sequence[Constraint],
    message: str,
    vocabulary: Sequence[str],
) -> NamedOrganisms:
    reading = _Reading(
        site_id=site_id,
        message=message,
        vocabulary=vocabulary,
        ask=no_decision if is_mock_deployment() else _ask_the_service,
        floor=get_settings().decisions_vocab_min_confidence,
    )
    named: list[Constraint] = []
    picks: list[OrganismPick] = []
    for c in constraints:
        words = c.organism
        if c.kind is not ConstraintKind.ORGANISM or words is None or not vocabulary:
            named.append(c)
            continue
        if not c.quote:
            named.append(c.model_copy(update={"value": None}))
            continue
        entry = completed_entry(words, message, vocabulary)
        if entry is not None:
            named.append(_named(c, entry))
            continue
        pick = await reading.pick(c.quote, words)
        settled = reading.settled(pick)
        if settled is not None:
            named.append(_named(c, settled))
            continue
        named.append(c.model_copy(update={"value": None}))
        picks.append(pick)
    return NamedOrganisms(constraints=named, picks=picks)


__all__ = [
    "FIT_QUESTION",
    "NONE_FITS",
    "ORGANISM_QUESTION",
    "NamedOrganisms",
    "fit_request",
    "named_organisms",
    "organism_request",
]
