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
        "step_proteins": "sequence",
        "step_taxon": "sequence",
        "step_and": "sequence",
    }
