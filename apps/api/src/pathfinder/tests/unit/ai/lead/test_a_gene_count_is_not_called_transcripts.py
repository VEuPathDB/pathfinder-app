"""A reply about a transcript strategy names its step counts as genes, the unit
the site counts them in; a count the strategy does not hold is left alone."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.lead.reply_claims import counts_named_as
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

# A reply over an orthology strategy whose four steps hold the counts below.
_TRANSCRIPT_COUNT_REPLY = (
    "The strategy now carries the source result into **Neospora caninum "
    "Liverpool** orthologs.\n\n- The existing signal-peptide criterion was kept.\n"
    "- The existing **2-99 transmembrane-domain** criterion was kept.\n- Their "
    "intersection contains **78 Toxoplasma gondii ME49 transcripts**.\n- The "
    "added **Transform by Orthology** search finds the orthologs of that 78-gene "
    "source result in **Neospora caninum Liverpool**, returning **145 "
    "transcripts**."
)
_COUNTS = {"s_sp": 720, "s_tm": 946, "s_and": 78, "s_orth": 145}


def _toxodb_turn(record_type: str) -> LeadDeps:
    graph = StrategyGraph(graph_id="g1", name="Neospora orthologs", site_id="toxodb")
    graph.record_type = record_type
    graph.steps = flatten_tree(
        StrategyStepNode(id="s_orth", search_name="GenesByOrthologs")
    )
    graph.recompute_roots()
    session = StrategySession(site_id="toxodb")
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts=dict(_COUNTS))
    state = pipeline_state(
        user_prompt="Carry these to their orthologs in Neospora caninum Liverpool.",
        user_message_id=uuid4(),
    )
    return lead_deps(state, strategy_session=session)


def _sentences(deps: LeadDeps, prose: str) -> list[str]:
    return [
        m.sentence
        for m in reconcile(reply(prose), turn_record(run_context_for(deps)))
        if m.kind == "counted_in_the_wrong_unit"
    ]


def test_a_transcript_count_the_strategy_holds_is_corrected_to_genes() -> None:
    assert _sentences(_toxodb_turn("transcript"), _TRANSCRIPT_COUNT_REPLY) == [
        (
            "The strategy holds transcript records, and the site counts them in "
            "genes: your reply writes 78 transcripts and 145 transcripts. Write "
            "78 genes and 145 genes."
        )
    ]


def test_a_reply_that_counts_genes_passes() -> None:
    prose = _TRANSCRIPT_COUNT_REPLY.replace("transcripts", "genes")

    assert _sentences(_toxodb_turn("transcript"), prose) == []


def test_a_transcript_count_the_strategy_does_not_hold_passes() -> None:
    prose = "The 145 genes come from 151 transcripts."

    assert _sentences(_toxodb_turn("transcript"), prose) == []


def test_a_pathway_strategy_is_counted_in_pathways() -> None:
    assert _sentences(_toxodb_turn("pathway"), "It returns 145 pathways.") == []


def test_a_strain_name_between_the_count_and_the_noun_is_read_through() -> None:
    prose = "The strategy returns **479 Plasmodium falciparum 3D7 transcripts** here."

    assert counts_named_as(prose, "transcript", instead_of="gene") == [479]


def test_a_second_number_stands_for_its_own_count() -> None:
    prose = "It returned 52 of 80 transcripts."

    assert counts_named_as(prose, "transcript", instead_of="gene") == [80]
