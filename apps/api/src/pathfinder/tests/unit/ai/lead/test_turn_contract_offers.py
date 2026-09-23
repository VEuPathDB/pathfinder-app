"""A reply that ends on a question records it: a proposal card for an offer,
``asked_questions`` for a value, or no question at all."""

from __future__ import annotations

import pytest

from pathfinder.ai.lead.reply_claims import ends_with_a_question
from pathfinder.ai.lead.turn_contract import reconcile, turn_record
from pathfinder.domain.strategy.constraints import ConstraintKind, OpenQuestion
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    building_deps,
    framing_deps,
    kinds,
    reply,
)

THE_OFFER = (
    "The strategy returns 4 genes. Verification found two limitations: the "
    "expression search does not exclude high expression at other time points, "
    "and the orthology profile does not encode 1:1:1 copy number.\n\n"
    "Would you like me to refine the strategy to enforce strict 3-hour "
    "specificity and independently verify 1:1:1 syntenic orthology?"
)
A_QUESTION_THEN_A_STATEMENT = (
    "Why did the count drop to 4? The orthology profile removed every gene "
    "without a copy in all three species.\n\nThe strategy holds 4 genes."
)


def _offer(**kwargs: bool) -> list[str]:
    deps = building_deps()
    for marker, value in kwargs.items():
        setattr(deps.state.turn_markers, marker, value)
    return kinds(deps, reply(THE_OFFER, changed=True, next_state="complete"))


class TestAReplyThatEndsOnAQuestion:
    def test_a_built_turn_that_ends_on_an_offer_is_refused(self) -> None:
        mismatches = reconcile(
            reply(THE_OFFER, changed=True, next_state="complete"),
            turn_record(run_context_for(building_deps())),
        )

        assert [m.kind for m in mismatches] == ["unrecorded_question"]
        assert "``propose_changes``" in mismatches[0].sentence
        assert "without a question" in mismatches[0].sentence

    def test_an_accepted_proposal_stands(self) -> None:
        assert _offer(accepted_proposal=True) == []

    def test_a_consult_that_ran_stands(self) -> None:
        assert _offer(consulted=True) == []

    def test_a_recorded_question_stands(self) -> None:
        report = reply(
            THE_OFFER,
            changed=True,
            next_state="complete",
            questions=[
                OpenQuestion(
                    question="Enforce strict 3-hour specificity?",
                    dimension=ConstraintKind.OTHER,
                    recommended_value="yes",
                )
            ],
        )

        assert kinds(building_deps(), report) == []

    def test_a_question_inside_the_reply_stands(self) -> None:
        report = reply(A_QUESTION_THEN_A_STATEMENT, changed=True, next_state="complete")

        assert kinds(building_deps(), report) == []

    def test_a_framed_turn_waiting_on_a_question_inside_its_reply_is_refused(
        self,
    ) -> None:
        mismatches = reconcile(
            reply(A_QUESTION_THEN_A_STATEMENT),
            turn_record(run_context_for(framing_deps())),
        )

        assert [m.kind for m in mismatches] == ["unrecorded_question"]
        assert "``propose_changes``" not in mismatches[0].sentence


@pytest.mark.parametrize(
    ("prose", "ends"),
    [
        ("Shall I refine it?", True),
        ("Shall I refine it?\n\n", True),
        ("**Shall I refine it?**", True),
        ('He asked "shall I refine it?"', True),
        ("Refine it (shall I?)", True),
        ("Shall I refine it? Say yes and I will.", False),
        ("Why did it drop?\n\nThe profile removed them.", False),
        ("The strategy holds 4 genes.", False),
        ("", False),
    ],
)
def test_the_last_paragraph_decides_whether_a_reply_ends_on_a_question(
    prose: str, ends: bool
) -> None:
    assert ends_with_a_question(prose) is ends
