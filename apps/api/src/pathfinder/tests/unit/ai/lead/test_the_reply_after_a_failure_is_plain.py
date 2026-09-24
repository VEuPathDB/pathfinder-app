"""A turn that ends with work undone says so in the user's own words.

The reply the user reads carries no tool name, no step id and no error code,
because none of them names anything the researcher can act on.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from pathfinder.ai.lead.contract_messages import (
    claimed_frame_message,
    unfinished_work_message,
)
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse, reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.build_outcome import BuildOutcome, StepPushFailure
from pathfinder.domain.strategy.constraints import ConstraintKind, OpenQuestion
from pathfinder.domain.strategy.spec_diff import SpecDiff
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reply
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
    user_intent,
)

A_REFUSED_EDIT = {"edit_strategy": 2}
THE_CHOICE = OpenQuestion(
    question="Which proteomics evidence should the filter require?",
    dimension=ConstraintKind.DATA_TYPE,
    recommended_value="two independent observations",
)
# The sentence the rule asks for: what did not work, and what was not done.
PLAIN = (
    "I could not add the mass-spec filter, so the strategy is unchanged. "
    "Should I require two independent proteomics observations?"
)
NAMES_A_TOOL = (
    "The edit_strategy pass was refused, so the strategy is unchanged. "
    "Should I require two independent proteomics observations?"
)
NAMES_A_STEP_ID = (
    "I could not write step_1a2b3c4d, so the strategy is unchanged. "
    "Should I require two independent proteomics observations?"
)
NAMES_AN_ERROR = (
    "The site refused the new step with HTTP 422, so the strategy is unchanged. "
    "Should I require two independent proteomics observations?"
)
# A count in the same range is a number the researcher asked for, however it is
# written.
REPORTS_A_COUNT = (
    "The mass-spec filter did not go on, so the strategy still returns 422 "
    "genes. Should I require two independent proteomics observations?"
)
REPORTS_A_HYPHENATED_COUNT = (
    "The mass-spec filter did not go on, so the strategy still holds a "
    "422-gene set. Should I require two independent proteomics observations?"
)
NAMES_A_RETRY = (
    "A ModelRetry came back from the pass, so the strategy is unchanged. "
    "Should I require two independent proteomics observations?"
)


def _editing_deps() -> LeadDeps:
    """A classified edit turn over a strategy, where ``edit_strategy`` is offered."""
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


def _kinds(
    deps: LeadDeps,
    report: LeadResponse,
    *,
    refused: dict[str, int] | None = None,
) -> list[str]:
    ctx = replace(run_context_for(deps), retries=dict(refused or {}))
    return [m.kind for m in reconcile(report, turn_record(ctx))]


def _sentence(
    deps: LeadDeps,
    report: LeadResponse,
    *,
    refused: dict[str, int] | None = None,
) -> str:
    ctx = replace(run_context_for(deps), retries=dict(refused or {}))
    found = [
        m for m in reconcile(report, turn_record(ctx)) if m.kind == "machine_words"
    ]
    return found[0].sentence if found else ""


def _answering(prose: str) -> LeadResponse:
    """A reply that records its question, so only the prose rule can fire."""
    return reply(prose, questions=[THE_CHOICE])


class TestAReplyAfterARefusedDispatch:
    def test_a_plain_sentence_stands(self) -> None:
        assert _kinds(_editing_deps(), _answering(PLAIN), refused=A_REFUSED_EDIT) == []

    def test_a_reply_that_names_the_tool_is_a_mismatch(self) -> None:
        found = _kinds(
            _editing_deps(), _answering(NAMES_A_TOOL), refused=A_REFUSED_EDIT
        )

        assert found == ["machine_words"]

    def test_the_correction_names_what_the_reply_printed(self) -> None:
        sentence = _sentence(
            _editing_deps(), _answering(NAMES_A_TOOL), refused=A_REFUSED_EDIT
        )

        assert "edit_strategy" in sentence
        assert "one plain sentence" in sentence

    def test_a_reply_that_names_a_step_id_is_a_mismatch(self) -> None:
        found = _kinds(
            _editing_deps(), _answering(NAMES_A_STEP_ID), refused=A_REFUSED_EDIT
        )

        assert found == ["machine_words"]

    def test_a_reply_that_names_an_error_code_is_a_mismatch(self) -> None:
        found = _kinds(
            _editing_deps(), _answering(NAMES_AN_ERROR), refused=A_REFUSED_EDIT
        )

        assert found == ["machine_words"]

    def test_a_gene_count_in_the_same_range_is_not_an_error_code(self) -> None:
        found = _kinds(
            _editing_deps(), _answering(REPORTS_A_COUNT), refused=A_REFUSED_EDIT
        )

        assert found == []

    def test_a_hyphenated_gene_count_is_not_an_error_code(self) -> None:
        found = _kinds(
            _editing_deps(),
            _answering(REPORTS_A_HYPHENATED_COUNT),
            refused=A_REFUSED_EDIT,
        )

        assert found == []

    def test_a_reply_that_names_the_retry_exception_is_a_mismatch(self) -> None:
        found = _kinds(
            _editing_deps(), _answering(NAMES_A_RETRY), refused=A_REFUSED_EDIT
        )

        assert found == ["machine_words"]


class TestTheRuleOnlyReadsAFailedTurn:
    def test_a_turn_with_no_refusal_and_no_stop_is_not_checked(self) -> None:
        assert _kinds(_editing_deps(), _answering(NAMES_A_TOOL)) == []

    def test_a_stopped_pass_is_checked(self) -> None:
        deps = _editing_deps()
        deps.last_phase_stop = PhaseStop(
            role="frame",
            reason=PhaseStopReason.BUDGET,
            tool_calls=60,
            criteria_bound=0,
            criteria_declared=4,
        )

        assert _kinds(deps, _answering(NAMES_A_STEP_ID)) == ["machine_words"]

    def test_a_push_that_lost_a_step_is_checked(self) -> None:
        deps = _editing_deps()
        deps.state.domain.last_build_outcome = BuildOutcome(
            pushed_step_ids=["s1"],
            failed_steps=[
                StepPushFailure(
                    step_id="step_1a2b3c4d",
                    search_name="GenesByMassSpec",
                    error="organism: Cannot be empty.",
                    wdk_status=422,
                ),
            ],
        )

        assert _kinds(deps, _answering(NAMES_AN_ERROR)) == ["machine_words"]


class TestTheCorrectionsAskForThePlainSentence:
    def test_the_unfinished_work_correction_asks_for_it(self) -> None:
        message = unfinished_work_message(("edit_strategy",), None)

        assert "one plain sentence" in message
        assert "no step id" in message

    def test_the_claimed_frame_correction_asks_for_it(self) -> None:
        message = claimed_frame_message(SpecDiff())

        assert "one plain sentence" in message
