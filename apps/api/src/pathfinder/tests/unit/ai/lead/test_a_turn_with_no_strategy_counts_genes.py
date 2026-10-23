"""A turn whose strategy holds no step yet counts in genes, as a turn with none
does, so a read-only count renders in the noun the researcher asked in."""

from __future__ import annotations

import pytest

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


@pytest.mark.parametrize(
    ("site_id", "noun"), [("amoebadb", "gene"), ("orthomcl", "protein")]
)
def test_an_empty_strategy_counts_the_sites_genes(site_id: str, noun: str) -> None:
    session = StrategySession(site_id=site_id)
    session.graph = StrategyGraph(graph_id="g1", name="", site_id=site_id)
    deps = lead_deps(
        pipeline_state(site_id, user_prompt="how many kinases?"),
        strategy_session=session,
    )

    assert turn_facts(deps).record_noun == noun


@pytest.mark.parametrize(
    ("site_id", "noun"), [("plasmodb", "gene"), ("orthomcl", "protein")]
)
def test_a_saved_set_of_no_record_type_counts_the_sites_genes(
    site_id: str, noun: str
) -> None:
    deps = lead_deps(
        pipeline_state(site_id), strategy_session=StrategySession(site_id=site_id)
    )
    deps.state.turn_markers.record_gene_set(
        CreatedGeneSet(id="gs_1", name="kinases", gene_count=3, record_type=None)
    )

    assert [fact.record_noun for fact in turn_facts(deps).saved] == [noun]
