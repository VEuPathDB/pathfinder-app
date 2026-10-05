"""An edit that withdraws a requirement and states the values that replace it
asks for a replacement: its correction names the change and the tool that makes
it, an analysis export's recut among them, and only a bare withdrawal names
delete_step."""

from __future__ import annotations

from veupathdb.domain.strategy import flatten_tree
from veupathdb_mcp.catalog import COMPUTE_QUERY

from pathfinder.ai.lead.contract_messages import unmade_change_message
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.eda_thread import OpenEdaAnalysis
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.tests._support.eda_step_doubles import DE_DATASET, export_step
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

# A vectorbase edit of a DESeq2 export that tightens its cut.
_WITHDRAWN = ["default cutoffs"]
_STATED = [
    "log2 fold change > 5",
    "p-value < 1e-10",
    "up-regulated genes only; none down-regulated",
]
_EXPORT = "step_e60c78ea"


def test_a_withdrawal_with_its_replacement_names_the_change_and_the_recut() -> None:
    assert unmade_change_message(_WITHDRAWN, _STATED, [_EXPORT]) == (
        "The message asks to replace 'default cutoffs' with 'log2 fold change > 5', "
        "'p-value < 1e-10', 'up-regulated genes only; none down-regulated' and this "
        "turn made no change and raised no card: make the change through "
        "edit_strategy, or through create_eda_step(replace_step_id='step_e60c78ea') "
        "for a change to an analysis export's cut, which needs no card, or say in "
        "the reply why the change cannot be made."
    )


def test_a_replacement_on_a_strategy_with_no_export_names_the_edit() -> None:
    assert unmade_change_message(["chromosome 17"], ["chromosome 19"], []) == (
        "The message asks to replace 'chromosome 17' with 'chromosome 19' and this "
        "turn made no change and raised no card: make the change through "
        "edit_strategy, or say in the reply why the change cannot be made."
    )


def test_a_bare_withdrawal_still_names_delete_step() -> None:
    assert unmade_change_message(["expressed during hyphal growth"], [], [_EXPORT]) == (
        "The message asks to remove 'expressed during hyphal growth' and this turn "
        "made no change and raised no card: remove it through delete_step, or say "
        "in the reply why it cannot be removed."
    )


def test_the_record_names_the_exports_of_the_open_analysis() -> None:
    session = StrategySession(site_id="vectorbase")
    graph = StrategyGraph(graph_id="g1", name="DE", site_id="vectorbase")
    graph.steps = flatten_tree(export_step("step_open", DE_DATASET))
    graph.note_analysis_kinds(
        {"step_open": StampedKind(search_name=COMPUTE_QUERY, kind=AnalysisKind.COMPUTE)}
    )
    session.graph = graph
    deps = lead_deps(pipeline_state("vectorbase"), strategy_session=session)
    closed = turn_record(run_context_for(deps)).export_step_ids
    deps.state.domain.open_eda_analysis = OpenEdaAnalysis(
        dataset_id=DE_DATASET, analysis_id="an_open_analysis"
    )

    assert (closed, turn_record(run_context_for(deps)).export_step_ids) == (
        (),
        ("step_open",),
    )
