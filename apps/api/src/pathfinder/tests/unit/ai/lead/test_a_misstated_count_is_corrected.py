"""A count the reply states for the strategy or a step is one a step holds."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import Mismatch, reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_ROOT_ONLY = {"s_taxon": 116}
_THREE_STEPS = {"s_taxon": 5_318, "s_text": 250, "s_and": 116}


def _plasmodb_turn(
    counts: dict[str, int],
    record_type: str = "gene",
    *,
    at_arrival: tuple[int, ...] = (),
) -> LeadDeps:
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id="plasmodb")
    graph.record_type = record_type
    graph.steps = flatten_tree(
        StrategyStepNode(id="s_taxon", search_name="GenesByTaxon")
    )
    graph.recompute_roots()
    session = StrategySession(site_id="plasmodb")
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts=dict(counts))
    state = pipeline_state(
        user_prompt="Find kinases in Plasmodium falciparum 3D7.",
        user_message_id=uuid4(),
    )
    state.turn_markers.counts_at_arrival = list(at_arrival)
    return lead_deps(state, strategy_session=session)


def _mismatches(deps: LeadDeps, prose: str) -> list[Mismatch]:
    return reconcile(reply(prose), turn_record(run_context_for(deps)))


def _sentences(deps: LeadDeps, prose: str) -> list[str]:
    return [m.sentence for m in _mismatches(deps, prose) if m.kind == "misstated_count"]


def test_a_count_no_step_holds_is_refused_with_the_count_the_root_holds() -> None:
    assert _sentences(
        _plasmodb_turn(_ROOT_ONLY), "The strategy returns 200 genes."
    ) == [
        (
            "Your reply states 200 genes for the strategy, and no step of it "
            "holds that count: its step holds 116 genes. State the count the "
            "site returned for the step you name."
        )
    ]


def test_every_step_count_is_named_when_several_steps_hold_one() -> None:
    prose = "The intersection step returns **1,200 genes**."

    assert _sentences(_plasmodb_turn(_THREE_STEPS), prose) == [
        (
            "Your reply states 1,200 genes for the strategy, and no step of it "
            "holds that count: its steps hold 5,318 genes, 250 genes and 116 "
            "genes. State the count the site returned for the step you name."
        )
    ]


def test_the_count_the_root_holds_passes() -> None:
    counts = {"s_taxon": 200}

    assert _sentences(_plasmodb_turn(counts), "The strategy returns 200 genes.") == []


def test_a_count_a_step_holds_passes() -> None:
    prose = (
        "The organism step returns 5,318 genes, and the strategy returns 116 "
        "genes after the intersection."
    )

    assert _sentences(_plasmodb_turn(_THREE_STEPS), prose) == []


def test_a_reply_with_no_count_passes() -> None:
    prose = "The strategy is built and verified."

    assert _mismatches(_plasmodb_turn(_ROOT_ONLY), prose) == []


def test_a_count_of_controls_or_sampled_genes_is_not_a_strategy_count() -> None:
    prose = (
        "The strategy returned all 12 positive control genes, and the check "
        "read 8 sampled genes from its result."
    )

    assert _sentences(_plasmodb_turn(_ROOT_ONLY), prose) == []


def test_a_count_in_a_clause_that_names_no_strategy_is_not_read() -> None:
    prose = "Your list names 30 genes."

    assert _sentences(_plasmodb_turn(_ROOT_ONLY), prose) == []


def test_a_count_in_the_wrong_unit_is_the_unit_rules_alone() -> None:
    prose = "The strategy returns 116 transcripts."

    kinds = [
        m.kind for m in _mismatches(_plasmodb_turn(_ROOT_ONLY, "transcript"), prose)
    ]

    assert kinds == ["counted_in_the_wrong_unit"]


def test_a_transcript_strategy_is_held_to_its_gene_count() -> None:
    prose = "The strategy returns 200 genes."

    assert _sentences(_plasmodb_turn(_ROOT_ONLY, "transcript"), prose) == [
        (
            "Your reply states 200 genes for the strategy, and no step of it "
            "holds that count: its step holds 116 genes. State the count the "
            "site returned for the step you name."
        )
    ]


def test_a_count_from_before_a_change_beside_a_held_count_passes() -> None:
    prose = (
        "The strategy now returns 1,203 genes, up from 116 genes when the two "
        "steps were intersected."
    )

    assert (
        _sentences(_plasmodb_turn({"s_sp": 479, "s_tm": 840, "s_or": 1_203}), prose)
        == []
    )


def test_a_top_n_in_a_sentence_about_the_result_passes() -> None:
    prose = (
        "The strategy returns 116 genes. The top 10 genes in the result by signal "
        "peptide score are listed below."
    )

    assert _sentences(_plasmodb_turn(_THREE_STEPS), prose) == []


def test_a_denominator_beside_the_step_count_passes() -> None:
    prose = (
        "The step returns 198 genes: 3 of the 201 genes the comparison kept are "
        "not in PlasmoDB's current annotation."
    )

    assert _sentences(_plasmodb_turn({"s_eda": 198}), prose) == []


def test_a_genome_count_beside_the_strategy_count_passes() -> None:
    prose = "Of the 5,318 protein-coding genes in 3D7, the strategy returns 479 genes."

    assert _sentences(_plasmodb_turn({"s_sp": 479}), prose) == []


def test_a_variant_count_in_a_sentence_naming_no_strategy_passes() -> None:
    prose = (
        "On the site SignalP-4.1 returns 76 of 80 positives and 1 of 40 negatives "
        "in 572 genes."
    )

    assert _sentences(_plasmodb_turn({"s_sp": 479}), prose) == []


def test_an_unmeasured_strategy_is_not_held_to_a_count() -> None:
    assert _sentences(_plasmodb_turn({}), "The strategy returns 200 genes.") == []


def test_a_removed_step_is_named_with_the_count_it_held_when_the_message_arrived() -> (
    None
):
    deps = _plasmodb_turn({"s_sp": 479}, at_arrival=(479, 840, 116))
    prose = "I removed the transmembrane-domain step (840 genes). The strategy returns 479 genes."

    assert _sentences(deps, prose) == []


def test_a_replaced_step_is_named_with_the_count_it_held_when_the_message_arrived() -> (
    None
):
    deps = _plasmodb_turn(
        {"s_sp": 479, "s_ex": 191, "s_and": 47}, at_arrival=(479, 840, 116)
    )
    prose = (
        "I replaced the transmembrane-domain step (840 genes) with the ExportPred "
        "search."
    )

    assert _sentences(deps, prose) == []


def test_a_recap_of_the_strategy_before_the_turn_passes() -> None:
    deps = _plasmodb_turn(
        {"s_sp": 479, "s_tm": 840, "s_or": 1_203}, at_arrival=(479, 840, 116)
    )

    assert _sentences(deps, "With Intersect the strategy returned 116 genes.") == []


def test_a_count_the_strategy_never_held_is_refused_whatever_it_held_before() -> None:
    deps = _plasmodb_turn(_ROOT_ONLY, at_arrival=(116,))

    assert _sentences(deps, "The strategy returns 200 genes.") == [
        (
            "Your reply states 200 genes for the strategy, and no step of it "
            "holds that count: its step holds 116 genes. State the count the "
            "site returned for the step you name."
        )
    ]
