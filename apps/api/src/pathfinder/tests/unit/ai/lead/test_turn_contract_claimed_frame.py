"""The claimed-frame rule: a criterion the reply reports is one the plan holds."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.parameters import NumberValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

CLAIMS_A_FRAME = (
    "I've framed the direct mass-spec evidence criterion without applying it "
    "yet. Please confirm the settings I recommend: at least two independent "
    "proteomics observations, and the merozoite dataset."
)
CLAIMS_AN_ADDITION = (
    "I added the direct mass-spec evidence requirement to the plan. It is not "
    "on the strategy until you confirm the thresholds."
)
SUMMARISES_THE_PLAN = (
    "The strategy combines the surface criterion with the merozoite stage "
    "criterion, and the root holds 316 genes."
)
_REQUEST = "Add a filter requiring direct mass-spec proteome evidence."


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


def _mass_spec() -> Criterion:
    return Criterion(
        id="c_mass_spec",
        text="detected in the merozoite proteome",
        search_name="GenesByMassSpec",
        resolved_params={"min_peptide_count": NumberValue(value=2)},
    )


def _framing_turn(*, recorded: bool) -> LeadDeps:
    """A turn that dispatched FRAME over a plan it entered with one criterion."""
    entered = _entered_with()
    plan = entered.model_copy(deep=True)
    if recorded:
        plan.criteria.append(_mass_spec())
    state = pipeline_state(
        user_prompt=_REQUEST,
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            operational_spec=plan,
            spec_before_turn=entered,
        ),
    )
    state.turn_markers.framed = True
    return lead_deps(state)


def test_a_framed_criterion_the_plan_does_not_hold_is_refused() -> None:
    deps = _framing_turn(recorded=False)

    assert kinds(deps, reply(CLAIMS_A_FRAME)) == ["claimed_frame"]


def test_the_same_claim_over_a_plan_that_took_it_passes() -> None:
    deps = _framing_turn(recorded=True)

    assert kinds(deps, reply(CLAIMS_A_FRAME)) == []


def test_an_addition_to_the_plan_the_plan_does_not_hold_is_refused() -> None:
    deps = _framing_turn(recorded=False)

    assert kinds(deps, reply(CLAIMS_AN_ADDITION)) == ["claimed_frame"]


def test_a_summary_of_the_plan_is_not_a_claim() -> None:
    deps = _framing_turn(recorded=False)

    assert kinds(deps, reply(SUMMARISES_THE_PLAN)) == []
