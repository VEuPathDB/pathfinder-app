"""A bare yes after a declined offer is refused, and never read as a build."""

from __future__ import annotations

import pytest
from assistant_core.graph.turn_state import PendingApproval

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.intent_gate import (
    DECLINED_OFFER_REFUSAL,
    bare_assent_refusal,
)
from pathfinder.ai.lead.proposal import DeclinedProposal
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import OpenQuestion
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_DECLINED = DeclinedProposal(
    question="Refine the strategy to require 1:1:1 syntenic orthologs?",
    proposed_changes=["Require 1:1:1 syntenic orthologs in Aedes aegypti"],
)


def _deps(prompt: str, *, declined: DeclinedProposal | None = _DECLINED) -> LeadDeps:
    domain = StrategyDomainState(declined_proposal=declined)
    return lead_deps(pipeline_state(user_prompt=prompt, domain=domain))


def test_the_refusal_is_the_fixed_sentence() -> None:
    assert DECLINED_OFFER_REFUSAL == (
        "You declined the last offer. Say what to change, or ask me to offer it again."
    )


@pytest.mark.parametrize("prompt", ["yes", "Yes, do it.", "ok, go ahead", "sure"])
def test_a_bare_yes_after_a_declined_offer_is_refused(prompt: str) -> None:
    assert bare_assent_refusal(_deps(prompt)) == DECLINED_OFFER_REFUSAL


def _with_open_card(deps: LeadDeps) -> LeadDeps:
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_propose", tool_name="propose_changes"
    )
    return deps


def _with_open_question(deps: LeadDeps) -> LeadDeps:
    deps.state.domain.open_questions = [
        OpenQuestion(question="Use the 3D7 strain?", recommended_value="3D7")
    ]
    return deps


def test_every_other_turn_takes_the_existing_classification() -> None:
    turns = {
        "no declined offer": _deps("yes", declined=None),
        "a card open to answer": _with_open_card(_deps("yes")),
        "a question open to answer": _with_open_question(_deps("yes")),
        "more than a yes": _deps("Yes, but only the Aedes orthologs."),
    }

    refusals = {name: bare_assent_refusal(deps) for name, deps in turns.items()}

    assert refusals == dict.fromkeys(turns)
