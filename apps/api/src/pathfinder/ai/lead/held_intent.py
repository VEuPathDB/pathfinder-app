"""The intent a reading of the researcher's words yields, held to the turn, the
site's organisms and genes, and the requirements the thread recorded."""

from __future__ import annotations

from collections.abc import Sequence

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
    ANSWERING_INTENTS,
    IntentClassification,
    NamedControls,
    UserIntent,
    untyped_ids,
)
from pathfinder.ai.lead.organism_reader import named_organisms
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import Constraint
from pathfinder.domain.strategy.reading_plan import plan_organisms
from pathfinder.domain.strategy.requirement_reports import numbered_requirements
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


def _ids_to_resolve(state: PipelineState, intent: UserIntent, said: str) -> list[str]:
    """The ids whose standing on the site decides a refusal of this intent."""
    if not _carries_a_file(state):
        return []
    return list(dict.fromkeys(untyped_ids(intent, said)))


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


async def read_the_site(
    state: PipelineState, intent: UserIntent, said: str
) -> SiteReading:
    """The organisms and genes of the site this intent is held to.

    Each gene the site resolves is a record this turn read.
    """
    organisms = (
        await list_organisms(state.site_id) if intent.explicit_constraints else []
    )
    asked = _ids_to_resolve(state, intent, said)
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
    state: PipelineState, intent: UserIntent, site: SiteReading, said: str
) -> list[str]:
    """The named ids neither the text types, the records the conversation
    showed last nor an attached file can show.

    The gate does not read a file; an id it may show is held when the site has it.
    """
    shown = {record.record_id.casefold() for record in state.domain.shown_records}
    untyped = [
        gene_id
        for gene_id in untyped_ids(intent, said)
        if gene_id.casefold() not in shown
    ]
    if not _carries_a_file(state):
        return untyped
    return [gene_id for gene_id in untyped if not site.holds(gene_id)]


def _without(intent: UserIntent, unheld: set[str]) -> UserIntent:
    if not unheld:
        return intent
    named = intent.named_controls
    controls = (
        None
        if named is None
        else NamedControls(
            positive_ids=[g for g in named.positive_ids if g not in unheld],
            negative_ids=[g for g in named.negative_ids if g not in unheld],
        )
    )
    return intent.model_copy(
        update={
            "named_controls": controls,
            "named_gene_ids": [g for g in intent.named_gene_ids if g not in unheld],
        }
    )


def _placed_beside(intent: UserIntent, held: Sequence[Constraint]) -> list[Constraint]:
    numbered = numbered_requirements(held)
    stated = [] if intent.request is None else intent.request.requirements
    beside = {r.quote: numbered[r.beside].id for r in stated if r.beside in numbered}
    return [
        c.model_copy(update={"beside": beside[c.quote]}) if c.quote in beside else c
        for c in intent.explicit_constraints
    ]


def _withdrawn_ids(intent: UserIntent, held: Sequence[Constraint]) -> list[str]:
    numbered = numbered_requirements(held)
    taken_back = [] if intent.request is None else intent.request.withdrawn
    return [numbered[w.requirement].id for w in taken_back if w.requirement in numbered]


async def hold_the_intent(deps: LeadDeps, intent: UserIntent, said: str) -> UserIntent:
    state = deps.state
    markers = state.turn_markers
    site = await read_the_site(state, intent, said)
    named = await named_organisms(
        state.site_id, intent.explicit_constraints, said, site.organisms
    )
    intent = intent.model_copy(update={"explicit_constraints": named.constraints})
    intent = _without(intent, set(_unheld_ids(state, intent, site, said)))
    held = state.domain.requirements
    intent = intent.model_copy(
        update={
            "withdrawn_ids": _withdrawn_ids(intent, held),
            "explicit_constraints": _placed_beside(intent, held),
        }
    )
    deps.intent = intent
    markers.intent_classified = True
    worked = markers.framed or markers.consulted or markers.changed_strategy
    if not worked and intent.classification is IntentClassification.NEW_STRATEGY:
        state.domain.take_a_new_request(strategy_has_steps=deps.step_count > 0)
    state.domain.record_intent(intent, request_text=said)
    state.domain.hold_organism_picks(named.picks)
    picked = state.domain.picked_offer(state.user_prompt)
    if picked is not None:
        state.domain.name_organisms_from(plan_organisms(picked.spec))
    if intent.classification in ANSWERING_INTENTS:
        state.domain.answer_the_questions_at_arrival(said)
    return intent


__all__ = ["SiteReading", "hold_the_intent", "read_the_site"]
