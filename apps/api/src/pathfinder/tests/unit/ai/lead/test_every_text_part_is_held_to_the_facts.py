"""Every text part a turn writes is held to the facts with its own correction:
a reply written after a card answer, under the same message, is checked
although the card's reply spent its correction."""

from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic_ai import DeferredToolRequests
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDenied

from pathfinder.ai.lead.card_contract import hold_the_contract_on_a_card
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import hold_the_turn_contract
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reading_deps, reply

# The toxodb replies under one message: the card's reply, then the reply after
# the card was answered. Neither number is in the facts.
_CARD_REPLY = "The export uses a log2 threshold of 0.5849625 for the cut."
_FINAL_REPLY = "The step now keeps genes at approximately 1.50004-fold."


def _spent(deps: LeadDeps) -> LeadDeps:
    """The markers of a message whose first run already spent its correction."""
    deps.state.turn_markers.contract_refused = True
    deps.state.turn_markers.facts_corrected = ["run-card:reply"]
    return deps


def test_the_reply_after_a_card_answer_is_checked_on_its_own_budget() -> None:
    deps = _spent(reading_deps())
    ctx = replace(run_context_for(deps), run_id="run-answer")

    answer = reply(_FINAL_REPLY)

    with pytest.raises(ModelRetry, match=r"1\.50004"):
        hold_the_turn_contract(ctx, answer)

    assert hold_the_turn_contract(ctx, answer) is answer


def test_a_reply_whose_run_spent_its_correction_goes_through() -> None:
    deps = _spent(reading_deps())
    ctx = replace(run_context_for(deps), run_id="run-card")

    answer = reply(_FINAL_REPLY)

    assert hold_the_turn_contract(ctx, answer) is answer


def test_a_cards_reply_is_checked_after_another_run_spent_its_correction() -> None:
    deps = _spent(reading_deps())
    ctx = replace(run_context_for(deps), run_id="run-answer")
    requests = DeferredToolRequests(
        approvals=[
            ToolCallPart(
                tool_name="consult_user",
                args={"questions": [], "reply": _CARD_REPLY},
                tool_call_id="call_card",
            )
        ]
    )

    results = hold_the_contract_on_a_card(ctx, requests)

    assert results is not None
    denial = results.approvals["call_card"]
    assert isinstance(denial, ToolDenied)
    assert "0.5849625" in denial.message
