"""The facts row shows a number at the precision the parameter's sheet gives it."""

from __future__ import annotations

from veupathdb.domain.parameters import SinglePickValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def test_the_row_shows_the_floor_at_four_digits() -> None:
    """tritrypdb RNA-Seq fold change: the floor term is a long decimal."""
    criterion = Criterion(
        id="c_fc",
        text="up in amastigotes",
        search_name="GenesByRNASeqFoldChange",
        resolved_params={
            "hard_floor": BoundValue(
                value=SinglePickValue(value="734.0197714535435"),
                source="chosen",
                display_name="Floor =",
                label="10 reads",
                number=True,
            ),
        },
    )
    state = pipeline_state(
        "tritrypdb",
        domain=StrategyDomainState(
            operational_spec=OperationalSpec(criteria=[criterion])
        ),
    )
    facts = turn_facts(lead_deps(state))

    assert facts.steps[0].parameters[0].lines() == ["Floor =: 734 (10 reads)"]
