"""The refusals the classification gate holds an intent to, read from the turn
and from the site's organisms, genes and record types."""

from __future__ import annotations

import re

from pydantic import ConfigDict, Field
from veupathdb.model import CamelModel
from veupathdb_mcp.audit import GeneIdRefusal, TooManyIdsError
from veupathdb_mcp.catalog import NoGeneRecordsError, get_discovery_service
from veupathdb_mcp.gene_lookup import (
    GeneIdFound,
    GeneIdReading,
    list_organisms,
    read_each_gene_id,
)

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.graph.turn_records import ReadRecord
from pathfinder.ai.lead.intent import (
    IntentClassification,
    UserIntent,
    named_ids,
    nothing_to_answer_message,
    occurs_in,
    question_asks_a_change_message,
    question_withdraws_message,
    unstated_ids_message,
    unstated_operator_refusal,
    untyped_ids,
)
from pathfinder.domain.strategy.organism_phrases import stated_organisms
from pathfinder.domain.strategy.words import FILLER_WORDS, words_of
from pathfinder.services.gene_records.read import gene_record_url

# A word that can be a gene id starts with a letter and holds a digit; the site
# decides which of them are genes.
_ID_CANDIDATE = re.compile(r"(?<![\w.])(?=[\w.-]*\d)[A-Za-z]\w*(?:[.-]\w+)*")


class RecordNames(CamelModel):
    model_config = ConfigDict(frozen=True)

    singular: str
    plural: str

    def shown(self) -> str:
        return f"{self.singular} ({self.plural})" if self.plural else self.singular

    def named_in(self, message: str) -> str | None:
        return next(
            (name for name in (self.plural, self.singular) if occurs_in(name, message)),
            None,
        )


def _record_names(site_id: str) -> tuple[RecordNames, ...]:
    held = get_discovery_service().held_record_types(site_id) or []
    return tuple(
        RecordNames(singular=rt.display_name, plural=rt.display_name_plural)
        for rt in held
        if rt.display_name
    )


class SiteReading(CamelModel):
    """What the gate read of the site for this classification."""

    model_config = ConfigDict(frozen=True)

    organisms: list[str] = Field(default_factory=list)
    genes: frozenset[str] = frozenset()
    """The asked ids that resolve to a gene of the site, case-folded."""
    unread: frozenset[str] = frozenset()
    records: tuple[RecordNames, ...] = ()

    def holds(self, gene_id: str) -> bool:
        return gene_id.casefold() in self.genes | self.unread


def _carries_a_file(state: PipelineState) -> bool:
    return any(part.type == "file" for part in state.user_parts)


def _ids_to_resolve(state: PipelineState, intent: UserIntent) -> list[str]:
    """The ids whose standing on the site decides a refusal of this intent."""
    asked = untyped_ids(intent, state.user_prompt) if _carries_a_file(state) else []
    if intent.classification is IntentClassification.OFF_TOPIC:
        asked += [*_ID_CANDIDATE.findall(state.user_prompt), *named_ids(intent)]
    return list(dict.fromkeys(asked))


async def _readings(site_id: str, asked: list[str]) -> list[GeneIdReading] | None:
    if not asked:
        return []
    try:
        return await read_each_gene_id(site_id, asked)
    except TooManyIdsError, NoGeneRecordsError:
        return None


def _found(readings: list[GeneIdReading]) -> list[GeneIdFound]:
    found: list[GeneIdFound] = []
    for reading in readings:
        match reading:
            case GeneIdFound():
                found.append(reading)
            case GeneIdRefusal():
                pass
    return found


async def read_the_site(state: PipelineState, intent: UserIntent) -> SiteReading:
    """The organisms and genes of the site this intent is held to.

    Each gene the site resolves is a record this turn read.
    """
    reads_organisms = bool(intent.explicit_constraints) or (
        intent.classification is IntentClassification.CONTEXT_STATEMENT
    )
    organisms = await list_organisms(state.site_id) if reads_organisms else []
    asked = _ids_to_resolve(state, intent)
    readings = await _readings(state.site_id, asked)
    found = [] if readings is None else _found(readings)
    state.turn_markers.record_resolved_genes(
        ReadRecord(
            record_id=gene.gene_id,
            url=gene_record_url(state.site_id, gene.gene_id),
            product=gene.product,
            organism=gene.organism,
        )
        for reading in found
        for gene in reading.records
    )
    off_topic = intent.classification is IntentClassification.OFF_TOPIC
    return SiteReading(
        records=_record_names(state.site_id) if off_topic else (),
        organisms=organisms,
        genes=frozenset(reading.given.casefold() for reading in found),
        unread=frozenset(g.casefold() for g in asked)
        if readings is None
        else frozenset(),
    )


def _off_topic_refusal(
    state: PipelineState, intent: UserIntent, site: SiteReading
) -> str | None:
    """Why an off-topic intent is in scope: the message names genes or a record
    type of the site."""
    if intent.classification is not IntentClassification.OFF_TOPIC:
        return None
    asked = _ids_to_resolve(state, intent)
    genes = [gene_id for gene_id in asked if gene_id.casefold() in site.genes]
    if genes:
        return (
            f"The message names {', '.join(genes)}, genes of this site, so it is in "
            "scope. Classify it by what it asks of them."
        )
    return _record_type_refusal(state.user_prompt, site.records)


def _record_type_refusal(message: str, records: tuple[RecordNames, ...]) -> str | None:
    named = next(
        (found for record in records if (found := record.named_in(message))), None
    )
    if named is None:
        return None
    held = ", ".join(record.shown() for record in records)
    return (
        f'The message names "{named}", a record type of this site, so it is in '
        f"scope. This site's records are: {held}. Classify it by what it asks of "
        "them."
    )


def _context_refusal(
    state: PipelineState, intent: UserIntent, site: SiteReading
) -> str | None:
    """Why a context statement asks for a build: it names an organism and more."""
    if intent.classification is not IntentClassification.CONTEXT_STATEMENT:
        return None
    message = state.user_prompt
    stated = stated_organisms(message, site.organisms)
    covered = {k for organism in stated for k in range(organism.start, organism.end)}
    rest = [w for k, w in enumerate(words_of(message)) if k not in covered]
    if not stated or not rest:
        return None
    names = ", ".join(f'"{organism.entry}"' for organism in stated)
    return (
        f"The message names {names}, an organism of this site, and what to find "
        f'in it ("{" ".join(rest)}"). A message that names an organism the site '
        "holds and a gene class or a search term asks for a build, whatever its "
        "grammar: classify it new_strategy on a conversation with no strategy "
        "and extend_strategy otherwise."
    )


def _unheld_ids(
    state: PipelineState, intent: UserIntent, site: SiteReading
) -> list[str]:
    """The named ids neither the text types nor an attached file can show.

    The gate does not read a file; an id it may show is held when the site has it.
    """
    untyped = untyped_ids(intent, state.user_prompt)
    if not _carries_a_file(state):
        return untyped
    return [gene_id for gene_id in untyped if not site.holds(gene_id)]


def _answers_nothing(state: PipelineState, intent: UserIntent) -> bool:
    """Whether the intent answers a question on a turn that holds none."""
    return (
        intent.classification is IntentClassification.CLARIFICATION_RESPONSE
        and not state.turn_markers.questions_at_arrival
        and state.pending_approval is None
    )


_REQUESTS = frozenset(
    {IntentClassification.EDIT_STRATEGY, IntentClassification.EXTEND_STRATEGY}
)

# The words of an ask that requests a check of the strategy. A check runs a
# building tool, so such an ask is never a question.
_CHECK_WORDS = frozenset(
    {
        "test",
        "check",
        "recheck",
        "verify",
        "validate",
        "control",
        "controls",
    }
)


def _content_words(text: str) -> set[str]:
    return {word for word in words_of(text) if word not in FILLER_WORDS}


def _words_outside_the_asks(state: PipelineState, intent: UserIntent) -> set[str]:
    """The content words of the message that none of its asks holds."""
    rest = state.user_prompt.casefold()
    for ask in intent.asks:
        rest = rest.replace(ask.casefold(), " ")
    return _content_words(rest)


def held_as_question(state: PipelineState, intent: UserIntent) -> UserIntent | None:
    """The question form of a change the intent records, or None.

    The message states nothing outside its asks: no word of a requirement the
    intent records, or no word at all when it records none. An ask that names
    a check keeps the request, and so does an intent marked as asking a change.
    """
    if intent.classification not in _REQUESTS or not intent.asks:
        return None
    if any(_CHECK_WORDS.intersection(words_of(ask)) for ask in intent.asks):
        return None
    if intent.edit_direction != "other" or intent.withdrawn:
        return None
    if intent.asks_a_change:
        return None
    outside = _words_outside_the_asks(state, intent)
    stated = {
        w
        for c in intent.explicit_constraints
        for w in _content_words(c.requested_value)
    }
    if outside & stated if stated else outside:
        return None
    return intent.as_question()


def classification_refusal(
    state: PipelineState, intent: UserIntent, site: SiteReading
) -> str | None:
    """Why this intent does not describe the turn's message, or None."""
    message = state.user_prompt
    operator = unstated_operator_refusal(intent, message)
    if operator is not None:
        return operator
    if intent.classification is IntentClassification.FOLLOW_UP_QUESTION and (
        intent.asks_a_change
    ):
        return question_asks_a_change_message()
    if intent.classification is IntentClassification.FOLLOW_UP_QUESTION and (
        intent.withdrawn
    ):
        return question_withdraws_message(
            [c.requested_value for c in intent.withdrawn],
            states_a_change=bool(_words_outside_the_asks(state, intent)),
        )
    if _answers_nothing(state, intent):
        return nothing_to_answer_message()
    unheld = _unheld_ids(state, intent, site)
    if unheld:
        return unstated_ids_message(unheld)
    return _off_topic_refusal(state, intent, site) or _context_refusal(
        state, intent, site
    )
