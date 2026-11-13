from __future__ import annotations

from strategist.ai.agents.state import CreatedGeneSet
from strategist.ai.graph.state import StrategyDomainState
from strategist.domain.evidence import NamedControlSet
from strategist.tests._support.separation import (
    ATTACHED_CONTROLS,
    TASK_ID,
    recorded_offer,
)


def _owners_domain() -> StrategyDomainState:
    return StrategyDomainState(
        original_request="Kinases on chromosome 3",
        created_gene_sets=[CreatedGeneSet(id="gs-1", name="kinase hits", gene_count=2)],
        separation_offers={str(TASK_ID): recorded_offer()},
        attached_controls=ATTACHED_CONTROLS,
        control_sets=[NamedControlSet(id="cs-1", name="owner controls")],
        memory_index={"case": 3, "knowledge": 1},
        shown_memories=["case:9b73"],
    )


def test_a_copy_for_another_account_drops_what_names_the_owners_account() -> None:
    copied = _owners_domain().for_another_account()

    assert copied.created_gene_sets == []
    assert copied.separation_offers == {}
    assert copied.attached_controls is None
    assert copied.control_sets == []
    assert copied.memory_index == {}
    assert copied.shown_memories == []


def test_a_copy_for_another_account_keeps_the_research() -> None:
    assert _owners_domain().for_another_account().original_request == (
        "Kinases on chromosome 3"
    )
