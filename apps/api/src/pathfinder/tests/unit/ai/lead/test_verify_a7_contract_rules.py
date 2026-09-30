"""Attacks on the ``claimed_frame`` contract rule.

Each test states one reply the release verifier constructed, and asserts how
the rule reads it.
"""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.questions import AskedQuestion
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import (
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


class TestClaimedFrameOverAnEmptyDiff:
    def test_a_denial_with_no_new_criterion_passes(self) -> None:
        assert (
            _claimed_frame_kinds(
                "The plan already holds a mass-spec criterion; nothing new was framed."
            )
            == []
        )

    def test_a_summary_of_criteria_framed_earlier_passes(self) -> None:
        assert (
            _claimed_frame_kinds("The strategy combines four criteria framed earlier.")
            == []
        )

    def test_the_plain_sentence_passes(self) -> None:
        assert (
            _claimed_frame_kinds(
                "I could not add the mass-spec filter, so the strategy is unchanged."
            )
            == []
        )

    def test_a_planned_next_step_naming_a_filter_is_refused(self) -> None:
        assert _claimed_frame_kinds(
            "I've planned the next step: add a mass-spec filter once you confirm."
        ) == ["claimed_frame"]

    def test_nothing_was_added_to_the_plan_passes(self) -> None:
        assert _claimed_frame_kinds("Nothing was added to the plan.") == []

    def test_i_framed_nothing_because_that_filter_exists_passes(self) -> None:
        assert (
            _claimed_frame_kinds(
                "I framed nothing, because that filter already exists."
            )
            == []
        )

    def test_a_report_of_a_refused_plan_passes(self) -> None:
        assert (
            _claimed_frame_kinds(
                "I planned to add a filter to the plan, but the site refused it."
            )
            == []
        )
