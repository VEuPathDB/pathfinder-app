from __future__ import annotations

from uuid import uuid4

import pytest
from veupathdb.domain.strategy import StrategyStepNode

from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.lead.turn_facts import turn_facts
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
)
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.classed_strategy import classed_steps
from strategist.tests.unit.ai.lead._one_sided_rows import (
    bound_value,
    count_of,
    text_value,
)
from strategist.tests.unit.ai.lead.conftest import (
    domain_answering,
    lead_deps,
    pipeline_state,
)

_MAX_WEIGHT = "max_molecular_weight"


def _weight_deps(*, built: bool) -> LeadDeps:
    held = count_of("molecular weight", "<", 30, "under 30 kDa")
    spec = OperationalSpec(
        goal="small proteins",
        criteria=[
            Criterion(
                id="s_mw",
                text="under 30 kDa",
                search_name="GenesByMolecularWeight",
                answers=[RequirementLink(requirement=held.id, param=_MAX_WEIGHT)],
                resolved_params={
                    "min_molecular_weight": bound_value(
                        text_value("10000"), "default", "Min Molecular Weight"
                    ),
                    _MAX_WEIGHT: bound_value(
                        text_value("30000"), "stated", "Max Molecular Weight"
                    ),
                },
            )
        ],
    )
    domain = domain_answering(spec)
    domain.requirements = [held]
    state = pipeline_state(
        "microsporidiadb",
        user_prompt="under 30 kDa",
        user_message_id=uuid4(),
        domain=domain,
    )
    if not built:
        return lead_deps(state, strategy_session=None)
    graph = StrategyGraph(graph_id="g1", name="w", site_id="microsporidiadb")
    graph.record_type = "transcript"
    graph.steps = classed_steps(
        StrategyStepNode(id="s_mw", search_name="GenesByMolecularWeight")
    )
    graph.recompute_roots()
    session = StrategySession(site_id="microsporidiadb")
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts={"s_mw": 926})
    return lead_deps(state, strategy_session=session)


@pytest.mark.parametrize("built", [True, False], ids=["built", "draft"])
def test_the_turn_shows_the_end_left_open(built: bool) -> None:
    [step] = turn_facts(_weight_deps(built=built)).steps

    assert step.lines()[1:] == [
        "Min Molecular Weight: 10000",
        "Max Molecular Weight: 30000",
        (
            "The request states 'under 30 kDa' and no lower bound. "
            "Site defaults this step holds: Min Molecular Weight 10000"
        ),
    ]
