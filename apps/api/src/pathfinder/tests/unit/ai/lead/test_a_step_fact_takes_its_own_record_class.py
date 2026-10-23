"""A built step's fact counts in the noun of the record class its search lists
under, and a combine takes the class of the steps it reads."""

from __future__ import annotations

from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.record_page import ListedRecord
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def _session() -> StrategySession:
    graph = StrategyGraph(graph_id="g1", name="strain gaps", site_id="orthomcl")
    graph.record_type = "sequence"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_and",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(
                id="step_proteins",
                search_name="FromGroups",
                primary_input=StrategyStepNode(
                    id="step_pattern", search_name="GroupsByPhyleticPattern"
                ),
            ),
            secondary_input=StrategyStepNode(id="step_taxon", search_name="ByTaxonomy"),
        )
    )
    graph.steps["step_pattern"].record_class = "group"
    graph.steps["step_proteins"].record_class = "sequence"
    graph.steps["step_taxon"].record_class = "sequence"
    graph.recompute_roots()
    session = StrategySession(site_id="orthomcl")
    session.graph = graph
    session.sync_state = WDKSyncState(
        step_counts={
            "step_pattern": 297,
            "step_proteins": 103766,
            "step_taxon": 5318,
            "step_and": 300,
        }
    )
    return session


def test_each_step_counts_in_its_own_record_class() -> None:
    facts = turn_facts(
        lead_deps(pipeline_state("orthomcl"), strategy_session=_session())
    )

    assert {step.step_id: step.record_noun for step in facts.steps} == {
        "step_pattern": "group",
        "step_proteins": "protein",
        "step_taxon": "protein",
        "step_and": "protein",
    }


def test_a_step_of_no_class_of_its_own_is_counted_as_records_not_as_the_strategys() -> (
    None
):
    session = _session()
    graph = session.graph
    assert graph is not None
    graph.record_type = "group"
    for step in graph.steps.values():
        step.record_class = None
    graph.steps["step_pattern"].record_class = "group"

    facts = turn_facts(lead_deps(pipeline_state("orthomcl"), strategy_session=session))

    assert {step.step_id: step.record_noun for step in facts.steps} == {
        "step_pattern": "group",
        "step_proteins": "record",
        "step_taxon": "record",
        "step_and": "record",
    }


def test_a_listing_of_a_step_of_no_class_links_no_record_page() -> None:
    session = _session()
    graph = session.graph
    assert graph is not None
    graph.steps["step_proteins"].record_class = None
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_pattern": 101, "step_proteins": 102}
    )
    deps = lead_deps(pipeline_state("orthomcl"), strategy_session=session)
    deps.state.turn_markers.record_listed_genes(101, ["OG7_0001234"])
    deps.state.turn_markers.record_listed_genes(102, ["hsap|ENSP00000216951"])

    facts = turn_facts(deps)

    assert [(fact.step_id, fact.records) for fact in facts.listed] == [
        (
            "step_pattern",
            [
                ListedRecord(
                    record_id="OG7_0001234",
                    url="https://qa.orthomcl.org/orthomcl.qa/app/record/group/OG7_0001234",
                )
            ],
        )
    ]


def test_a_strategy_of_no_known_class_counts_records() -> None:
    session = _session()
    graph = session.graph
    assert graph is not None
    graph.record_type = None

    facts = turn_facts(lead_deps(pipeline_state("orthomcl"), strategy_session=session))

    assert facts.record_noun == "record"
