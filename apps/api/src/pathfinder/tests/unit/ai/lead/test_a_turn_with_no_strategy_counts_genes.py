"""A turn whose strategy holds no step yet counts in genes, as a turn with none
does, so a read-only count renders in the noun the researcher asked in."""

from __future__ import annotations

from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def test_an_empty_strategy_counts_genes() -> None:
    session = StrategySession(site_id="amoebadb")
    session.graph = StrategyGraph(graph_id="g1", name="", site_id="amoebadb")
    deps = lead_deps(
        pipeline_state("amoebadb", user_prompt="how many kinases?"),
        strategy_session=session,
    )

    assert turn_facts(deps).record_noun == "gene"
