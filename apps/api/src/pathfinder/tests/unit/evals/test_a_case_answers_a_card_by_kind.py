"""A case states its gate policy, and each answer names the card and the turn it
answers; a case that must not build never accepts an offer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.evals.case import EvalCase, GateAnswer, GatePlan
from pathfinder.evals.store import load_corpus


def _raw(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "name": "a-case",
        "turns": ["Find kinases.", "Remove the text step."],
        "siteId": "plasmodb",
        "assistantId": "pathfinder",
        "rationale": "pins a thing",
        "expected": {"buildsStrategy": True},
        "provenance": {
            "site": "plasmodb",
            "assistant": "pathfinder",
            "origin": "cataloged-failure",
            "addedAt": "2026-09-30",
            "reference": "an-item.md",
        },
        "gates": {"policy": "leave"},
    }
    raw.update(overrides)
    return raw


def test_a_case_that_states_no_gate_policy_is_refused() -> None:
    raw = _raw()
    del raw["gates"]

    with pytest.raises(ValidationError, match="gates"):
        EvalCase.model_validate(raw)


def test_every_shipped_case_states_its_gate_policy() -> None:
    policies = {case.gates.policy for case in load_corpus()}

    assert policies <= {"auto", "stop", "decline-offers", "leave"}


def test_an_answer_names_the_card_and_the_turn_it_answers() -> None:
    case = EvalCase.model_validate(
        _raw(
            gates={
                "policy": "leave",
                "answers": [{"card": "delete_step", "turn": 1, "accept": True}],
            }
        )
    )

    assert case.gates.answers == [GateAnswer(card="delete_step", turn=1)]


def test_an_answer_for_a_turn_the_case_does_not_have_is_refused() -> None:
    with pytest.raises(ValidationError, match="turn 2"):
        EvalCase.model_validate(
            _raw(
                gates={
                    "policy": "leave",
                    "answers": [{"card": "delete_step", "turn": 2}],
                }
            )
        )


def test_picks_answer_a_question_card_only() -> None:
    with pytest.raises(ValidationError, match="question card"):
        GateAnswer(card="delete_step", turn=0, picks=["yes"])
    with pytest.raises(ValidationError, match="question card"):
        GateAnswer(card="consult_user", turn=0)


@pytest.mark.parametrize("policy", ["auto", "stop"])
def test_a_case_that_must_not_build_never_accepts_an_offer(policy: str) -> None:
    with pytest.raises(ValidationError, match="offer"):
        EvalCase.model_validate(
            _raw(expected={"buildsStrategy": False}, gates={"policy": policy})
        )


def test_a_one_turn_case_that_must_not_build_may_stop_at_its_card() -> None:
    case = EvalCase.model_validate(
        _raw(
            turns=["I'm investigating virulence factors."],
            expected={"buildsStrategy": False},
            gates={"policy": "stop"},
        )
    )

    assert case.gates.policy == "stop"


def _default(
    plan: GatePlan, card: str, *, offer: bool, final: bool
) -> GateAnswer | None:
    return plan.default_answer(card, turn=0, offer=offer, final=final)


def test_each_policy_answers_the_cards_no_answer_names() -> None:
    auto = GatePlan(policy="auto")
    stop = GatePlan(policy="stop")
    decline = GatePlan(policy="decline-offers")
    leave = GatePlan(policy="leave")

    assert [
        _default(auto, "propose_changes", offer=True, final=True),
        _default(auto, "consult_user", offer=False, final=False),
        _default(stop, "delete_step", offer=False, final=False),
        _default(stop, "delete_step", offer=False, final=True),
        _default(decline, "propose_changes", offer=True, final=False),
        _default(decline, "delete_step", offer=False, final=False),
        _default(decline, "consult_user", offer=False, final=False),
        _default(leave, "delete_step", offer=False, final=False),
    ] == [
        GateAnswer(card="propose_changes", turn=0),
        GateAnswer(card="consult_user", turn=0, picks=[]),
        GateAnswer(card="delete_step", turn=0),
        None,
        GateAnswer(card="propose_changes", turn=0, accept=False),
        GateAnswer(card="delete_step", turn=0),
        None,
        None,
    ]
