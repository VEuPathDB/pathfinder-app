"""Attacks on the ``claimed_frame`` and ``machine_words`` contract rules.

Each test states one reply the release verifier constructed, and asserts how
the rule reads it.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse, reconcile, turn_record
from pathfinder.domain.strategy.constraints import ConstraintKind, OpenQuestion
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
    user_intent,
)

THE_CHOICE = OpenQuestion(
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


def _editing_deps() -> LeadDeps:
    deps = lead_deps(
        pipeline_state(
            user_prompt="Add a mass-spec evidence filter.",
            user_message_id=uuid4(),
        ),
        intent=user_intent(IntentClassification.EDIT_STRATEGY),
        strategy_session=session_with_one_step(),
    )
    deps.state.turn_markers.intent_classified = True
    return deps


def _machine_kinds(prose: str, *, refused: dict[str, int] | None = None) -> list[str]:
    ctx = replace(run_context_for(_editing_deps()), retries=dict(refused or {}))
    report: LeadResponse = reply(prose, questions=[THE_CHOICE])
    return [
        m.kind for m in reconcile(report, turn_record(ctx)) if m.kind == "machine_words"
    ]


class TestMachineWordsAfterARefusedDispatch:
    def test_a_gene_count_passes(self) -> None:
        assert (
            _machine_kinds(
                "The site returned 422 genes, so I stopped. Which evidence?",
                refused=A_REFUSED_EDIT,
            )
            == []
        )

    def test_an_http_status_is_refused(self) -> None:
        assert _machine_kinds(
            "VEuPathDB answered HTTP 422, so nothing was added. Which evidence?",
            refused=A_REFUSED_EDIT,
        ) == ["machine_words"]

    def test_a_step_number_in_prose_passes(self) -> None:
        assert (
            _machine_kinds(
                "The ortholog step (step 3) was not changed. Which evidence?",
                refused=A_REFUSED_EDIT,
            )
            == []
        )

    def test_naming_the_act_in_plain_words_passes(self) -> None:
        assert (
            _machine_kinds(
                "I could not verify the strategy, so it is unchanged. Which evidence?",
                refused={"verify_strategy": 1},
            )
            == []
        )

    def test_the_identifier_form_is_refused(self) -> None:
        assert _machine_kinds(
            "I could not run verify_strategy. Which evidence?",
            refused={"verify_strategy": 1},
        ) == ["machine_words"]

    def test_a_success_turn_mentioning_the_retry_is_not_checked(self) -> None:
        assert _machine_kinds("A ModelRetry is not a thing here. Which evidence?") == []

    def test_the_lead_tool_names_are_refused(self) -> None:
        """The approval tools the Lead calls itself are identifiers too."""
        assert _machine_kinds(
            "The delete_step call was declined and clear_strategy was not "
            "offered; consult_user came back empty. Which evidence?",
            refused=A_REFUSED_EDIT,
        ) == ["machine_words"]

    def test_a_hyphenated_gene_count_passes(self) -> None:
        assert (
            _machine_kinds(
                "The intersection left a 422-gene set unchanged. Which evidence?",
                refused=A_REFUSED_EDIT,
            )
            == []
        )

    def test_a_capitalised_error_code_is_refused(self) -> None:
        assert _machine_kinds(
            "Error 422 came back from the site. Which evidence?",
            refused=A_REFUSED_EDIT,
        ) == ["machine_words"]
