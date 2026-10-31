"""The refusals the classification gate holds an intent to, read from the turn
and from the site's organisms and genes."""

from __future__ import annotations

from pydantic import ConfigDict, Field
from veupathdb.model import CamelModel
from veupathdb_mcp.audit import GeneIdRefusal, TooManyIdsError
from veupathdb_mcp.catalog import NoGeneRecordsError
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
    nothing_to_answer_message,
    question_asks_a_change_message,
    question_withdraws_message,
    unstated_ids_message,
    untyped_ids,
)
from pathfinder.services.gene_records.read import gene_record_url


class SiteReading(CamelModel):
    """What the gate read of the site for this classification."""

    model_config = ConfigDict(frozen=True)

    organisms: list[str] = Field(default_factory=list)
    genes: frozenset[str] = frozenset()
    """The asked ids that resolve to a gene of the site, case-folded."""
    unread: frozenset[str] = frozenset()

    def holds(self, gene_id: str) -> bool:
        return gene_id.casefold() in self.genes | self.unread


def _carries_a_file(state: PipelineState) -> bool:
    return any(part.type == "file" for part in state.user_parts)


def _ids_to_resolve(state: PipelineState, intent: UserIntent) -> list[str]:
    """The ids whose standing on the site decides a refusal of this intent."""
    if not _carries_a_file(state):
        return []
    return list(dict.fromkeys(untyped_ids(intent, state.user_prompt)))


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
    organisms = (
        await list_organisms(state.site_id) if intent.explicit_constraints else []
    )
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
    return SiteReading(
        organisms=organisms,
        genes=frozenset(reading.given.casefold() for reading in found),
        unread=frozenset(g.casefold() for g in asked)
        if readings is None
        else frozenset(),
    )


def _unheld_ids(
    state: PipelineState, intent: UserIntent, site: SiteReading
) -> list[str]:
    """The named ids neither the text types, the records the conversation
    showed last nor an attached file can show.

    The gate does not read a file; an id it may show is held when the site has it.
    """
    shown = {record.record_id.casefold() for record in state.domain.shown_records}
    untyped = [
        gene_id
        for gene_id in untyped_ids(intent, state.user_prompt)
        if gene_id.casefold() not in shown
    ]
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


def classification_refusal(
    state: PipelineState, intent: UserIntent, site: SiteReading
) -> str | None:
    """Why this intent does not describe the turn's message, or None."""
    if intent.classification is IntentClassification.FOLLOW_UP_QUESTION and (
        intent.asks_a_change
    ):
        return question_asks_a_change_message()
    if intent.classification is IntentClassification.FOLLOW_UP_QUESTION and (
        intent.withdrawn
    ):
        return question_withdraws_message([c.requested_value for c in intent.withdrawn])
    if _answers_nothing(state, intent):
        return nothing_to_answer_message()
    unheld = _unheld_ids(state, intent, site)
    return unstated_ids_message(unheld) if unheld else None
