"""A reply that ends on a question records it: a proposal card for an offer,
the question card for a value the frame left open, ``asked_questions`` for any
other value, or no question at all."""

from __future__ import annotations

from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.questions import AskedQuestion
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    building_deps,
    kinds,
    open_frame_deps,
    reply,
)

THE_OFFER = (
    "The strategy is built. Verification found two limitations: the "
    "expression search does not exclude high expression at other time points, "
    "and the orthology profile does not encode single-copy orthologs.\n\n"
    "Would you like me to refine the strategy to enforce strict early "
    "specificity and independently verify single-copy syntenic orthology?"
)
A_QUESTION_THEN_A_STATEMENT = (
    "Why did the count drop? The orthology profile removed every gene "
    "without a copy in every species you named.\n\nThe count is shown beside this reply."
)


def _offer(**kwargs: bool) -> list[str]:
    deps = building_deps()
    for marker, value in kwargs.items():
        setattr(deps.state.turn_markers, marker, value)
    return kinds(deps, reply(THE_OFFER, next_state="complete"))


class TestAReplyThatEndsOnAQuestion:
    def test_an_accepted_proposal_stands(self) -> None:
        assert _offer(accepted_proposal=True) == []

    def test_a_consult_that_ran_stands(self) -> None:
        assert _offer(consulted=True) == []

    def test_a_recorded_question_stands(self) -> None:
        report = reply(
            THE_OFFER,
            next_state="complete",
            questions=[
                AskedQuestion(
                    question="Enforce strict 3-hour specificity?",
                    dimension=ConstraintKind.OTHER,
                    recommended_value="yes",
                )
            ],
        )

        assert kinds(building_deps(), report) == []

    def test_a_question_inside_the_reply_stands(self) -> None:
        report = reply(A_QUESTION_THEN_A_STATEMENT, next_state="complete")

        assert kinds(building_deps(), report) == []

    def test_an_open_frame_s_question_inside_its_reply_asks_for_the_card(
        self,
    ) -> None:
        mismatches = reconcile(
            reply(A_QUESTION_THEN_A_STATEMENT),
            turn_record(run_context_for(open_frame_deps())),
        )

        assert [m.kind for m in mismatches] == ["open_value_in_prose"]
        assert "``propose_changes``" not in mismatches[0].sentence
