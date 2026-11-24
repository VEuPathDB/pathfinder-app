"""A build no check saw shows the system's status beside any reply, and no rule
reads the word "verified" in the reply."""

from __future__ import annotations

import pytest
from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ToolCallPart

from strategist.ai.lead.card_contract import hold_the_contract_on_a_card
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.lead.turn_contract import LeadResponse, hold_the_turn_contract
from strategist.ai.lead.turn_record import turn_record
from strategist.domain.turn_facts import UNVERIFIED_BUILD
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead._turn_contract_cases import building_deps

_CLAIMS_A_CHECK = "I added the step and verified it."
_SAYS_VERIFIED = [
    "The new step still needs to be verified before you rely on it.",
    "Once the site answers, the result can be verified.",
    "The strategy you verified last turn now has a third step.",
    "Would you like the new step verified now?",
    "The top hit is YAL001C, Verified ORF, subunit of TFIIIC.",
    "I verified the count against the site's own count.",
]


def _unverified_status(deps: LeadDeps) -> str:
    return turn_record(run_context_for(deps)).facts.unverified


def _card(reply: str) -> DeferredToolRequests:
    return DeferredToolRequests(
        approvals=[
            ToolCallPart(
                tool_name="consult_user",
                args={"questions": [], "reply": reply},
                tool_call_id="call_card",
            )
        ]
    )


@pytest.mark.parametrize("sentence", [*_SAYS_VERIFIED, _CLAIMS_A_CHECK])
def test_a_reply_that_says_verified_passes_beside_the_status(sentence: str) -> None:
    deps = building_deps(verified=False)
    answer = LeadResponse(prose=sentence)

    assert hold_the_turn_contract(run_context_for(deps), answer) == answer
    markers = deps.state.turn_markers
    assert (markers.answer_ledger.uses, markers.unchecked_reply) == ((), False)
    assert _unverified_status(deps) == UNVERIFIED_BUILD


@pytest.mark.parametrize("sentence", [*_SAYS_VERIFIED, _CLAIMS_A_CHECK])
def test_a_card_that_says_verified_passes_beside_the_status(sentence: str) -> None:
    deps = building_deps(verified=False)

    results = hold_the_contract_on_a_card(run_context_for(deps), _card(sentence))

    assert results is None
    markers = deps.state.turn_markers
    assert (markers.answer_ledger.uses, markers.unchecked_reply) == ((), False)
    assert _unverified_status(deps) == UNVERIFIED_BUILD


def test_a_turn_that_verified_shows_no_unverified_status() -> None:
    assert _unverified_status(building_deps(verified=True)) == ""
