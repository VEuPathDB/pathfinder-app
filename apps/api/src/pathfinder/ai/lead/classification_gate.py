"""The refusals the classification gate holds an intent to, read from the turn
and from the site's organisms and genes."""

from __future__ import annotations

import re

from pydantic import ConfigDict, Field
from veupathdb.model import CamelModel
from veupathdb_mcp.gene_lookup import list_organisms, resolve_gene_ids

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.graph.turn_records import ReadRecord
from pathfinder.ai.lead.intent import (
    IntentClassification,
    UserIntent,
    named_ids,
    nothing_to_answer_message,
    unstated_ids_message,
    unstated_operator_refusal,
    untyped_ids,
)
from pathfinder.domain.strategy.organism_phrases import stated_organisms
from pathfinder.domain.strategy.requirement_lifecycle import unheld_withdrawals
from pathfinder.domain.strategy.words import FILLER_WORDS, words_of
from pathfinder.services.gene_records.read import gene_record_url

# A word that can be a gene id starts with a letter and holds a digit; the site
# decides which of them are genes.
_ID_CANDIDATE = re.compile(r"(?<![\w.])(?=[\w.-]*\d)[A-Za-z]\w*(?:[.-]\w+)*")


class SiteReading(CamelModel):
    """What the gate read of the site for this classification."""

    model_config = ConfigDict(frozen=True)

    organisms: list[str] = Field(default_factory=list)
    genes: frozenset[str] = frozenset()
    """The asked ids that resolve to a gene of the site, case-folded."""


def _carries_a_file(state: PipelineState) -> bool:
    return any(part.type == "file" for part in state.user_parts)


def _ids_to_resolve(state: PipelineState, intent: UserIntent) -> list[str]:
    """The ids whose standing on the site decides a refusal of this intent."""
    asked = untyped_ids(intent, state.user_prompt) if _carries_a_file(state) else []
    if intent.classification is IntentClassification.OFF_TOPIC:
        asked += [*_ID_CANDIDATE.findall(state.user_prompt), *named_ids(intent)]
    return list(dict.fromkeys(asked))


async def read_the_site(state: PipelineState, intent: UserIntent) -> SiteReading:
    """The organisms and genes of the site this intent is held to.

    Each gene the site resolves is a record this turn read.
    """
    reads_organisms = bool(intent.explicit_constraints) or (
        intent.classification is IntentClassification.CONTEXT_STATEMENT
    )
    organisms = await list_organisms(state.site_id) if reads_organisms else []
    asked = _ids_to_resolve(state, intent)
    resolved = await resolve_gene_ids(state.site_id, asked) if asked else None
    genes = [] if resolved is None else resolved.records
    state.turn_markers.record_resolved_genes(
        ReadRecord(
            record_id=gene.gene_id,
            url=gene_record_url(state.site_id, gene.gene_id),
            product=gene.product,
            organism=gene.organism,
        )
        for gene in genes
    )
    return SiteReading(
        organisms=organisms,
        genes=frozenset(gene.gene_id.casefold() for gene in genes),
    )


def _off_topic_refusal(
    state: PipelineState, intent: UserIntent, site: SiteReading
) -> str | None:
    """Why an off-topic intent is in scope: the message names genes of the site."""
    if intent.classification is not IntentClassification.OFF_TOPIC:
        return None
    asked = _ids_to_resolve(state, intent)
    genes = [gene_id for gene_id in asked if gene_id.casefold() in site.genes]
    if not genes:
        return None
    return (
        f"The message names {', '.join(genes)}, genes of this site, so it is in "
        "scope. Classify it by what it asks of them."
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
    return [gene_id for gene_id in untyped if gene_id.casefold() not in site.genes]


def _answers_nothing(state: PipelineState, intent: UserIntent) -> bool:
    """Whether the intent answers a question on a turn that holds none."""
    return (
        intent.classification is IntentClassification.CLARIFICATION_RESPONSE
        and not state.turn_markers.questions_at_arrival
        and state.pending_approval is None
    )


def _withdrawal_refusal(state: PipelineState, intent: UserIntent) -> str | None:
    """Why a withdrawal names a requirement nobody holds, or a successor that
    the message does not state or that the conversation holds already."""
    held = state.domain.requirements
    held_keys = {c.key for c in held}
    stated = {c.key for c in intent.explicit_constraints}
    successors = [w.replaced_by for w in intent.withdrawn_requirements if w.replaced_by]
    found = [
        *(
            f"{key!r} names no requirement the conversation holds"
            for key in unheld_withdrawals(intent.withdrawn_requirements, held=held)
        ),
        *(
            f"{key!r} is a requirement the conversation already holds, so it "
            "replaces nothing"
            for key in successors
            if key in held_keys
        ),
        *(
            f"{key!r} replaces it, but explicit_constraints states no such requirement"
            for key in successors
            if key not in held_keys and key not in stated
        ),
    ]
    if not found:
        return None
    keys = ", ".join(repr(c.key) for c in held) or "none"
    return (
        f"withdrawn_requirements: {'; '.join(found)}. The requirements it holds: "
        f"{keys}. An empty replacedBy removes the requirement; a replacedBy names "
        "a requirement this message states for the first time."
    )


_REQUESTS = frozenset(
    {IntentClassification.EDIT_STRATEGY, IntentClassification.EXTEND_STRATEGY}
)


def _content_words(text: str) -> set[str]:
    return {word for word in words_of(text) if word not in FILLER_WORDS}


def _question_refusal(state: PipelineState, intent: UserIntent) -> str | None:
    """Why a change the intent records is a question about the strategy.

    The message states nothing outside its asks: no word of a requirement the
    intent records, or no word at all when it records none.
    """
    if intent.classification not in _REQUESTS or not intent.asks:
        return None
    if intent.edit_direction != "other" or intent.withdrawn_requirements:
        return None
    rest = state.user_prompt.casefold()
    for ask in intent.asks:
        rest = rest.replace(ask.casefold(), " ")
    outside = _content_words(rest)
    stated = {
        w
        for c in intent.explicit_constraints
        for w in _content_words(c.requested_value)
    }
    if outside & stated if stated else outside:
        return None
    return (
        f"The message states no change outside its questions ({'; '.join(intent.asks)}). "
        "A question about what the strategy holds, whether a change went "
        "through or what the count is now, is a follow_up_question: the facts "
        "answer it and nothing is framed. If the message asks for a change, "
        "asks lists only the words that ask for an answer, and the change goes "
        "in explicit_constraints."
    )


def classification_refusal(
    state: PipelineState, intent: UserIntent, site: SiteReading
) -> str | None:
    """Why this intent does not describe the turn's message, or None."""
    message = state.user_prompt
    operator = unstated_operator_refusal(intent, message)
    if operator is not None:
        return operator
    if _answers_nothing(state, intent):
        return nothing_to_answer_message()
    withdrawal = _withdrawal_refusal(state, intent)
    if withdrawal is not None:
        return withdrawal
    question = _question_refusal(state, intent)
    if question is not None:
        return question
    unheld = _unheld_ids(state, intent, site)
    if unheld:
        return unstated_ids_message(unheld)
    return _off_topic_refusal(state, intent, site) or _context_refusal(
        state, intent, site
    )
