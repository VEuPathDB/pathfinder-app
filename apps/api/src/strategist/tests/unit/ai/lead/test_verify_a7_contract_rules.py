"""Attacks on the ``claimed_frame`` contract rule.

Each test states one reply the release verifier constructed, and asserts how
the rule reads it.
"""

from __future__ import annotations

from uuid import uuid4

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.domain.strategy.constraints import ConstraintKind
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.questions import AskedQuestion
from strategist.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from strategist.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
)

THE_CHOICE = AskedQuestion(
    question="Which proteomics evidence should the filter require?",
    dimension=ConstraintKind.DATA_TYPE,
    recommended_value="two independent observations",
)
A_REFUSED_EDIT = {"edit_strategy": 2}


def _entered_with() -> OperationalSpec:
    return OperationalSpec(
        goal="vaccine candidates",
        criteria=[
            Criterion(
                id="c_surface",
                text="predicted surface proteins",
                search_name="GenesBySignalPeptide",
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="c_surface")
        ),
    )


def _framing_turn_over_an_empty_diff() -> LeadDeps:
    entered = _entered_with()
    state = pipeline_state(
        user_prompt="Add a filter requiring direct mass-spec proteome evidence.",
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            operational_spec=entered.model_copy(deep=True),
            spec_before_turn=entered,
        ),
    )
    state.turn_markers.framed = True
    return lead_deps(state)


def _claimed_frame_kinds(prose: str) -> list[str]:
    return [
        k
        for k in kinds(_framing_turn_over_an_empty_diff(), reply(prose))
        if k == "claimed_frame"
    ]
