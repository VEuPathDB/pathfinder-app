from __future__ import annotations

import asyncio

import pytest
from pydantic_ai import DeferredToolRequests
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.lead.card_contract import hold_the_contract_on_a_card
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse, hold_the_turn_contract
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.turn_facts import UNVERIFIED_BUILD
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import building_deps

_WHY = "the verification pass stopped on its call budget"
_STATES_WHY = f"I added the step. I cannot verify it right now because {_WHY}."
_CLAIMS_A_CHECK = "I added the step and verified it."
_SAYS_VERIFIED = [
    "The new step still needs to be verified before you rely on it.",
    "Once the site answers, the result can be verified.",
    "The strategy you verified last turn now has a third step.",
    "Would you like the new step verified now?",
    "The top hit is YAL001C, Verified ORF, subunit of TFIIIC.",
    "I verified the count against the site's own count.",
]
_ASKED = (
    "Call verify_strategy, or set `unverifiedReason` to why it cannot run and "
    "state it in your reply."
)
_ASKED_TO_TRY = (
    "Call verify_strategy. `unverifiedReason` is accepted only after a check of "
    "this turn stopped or was refused."
)


def _stopped(role: PhaseRole = "verification") -> LeadDeps:
    deps = building_deps(verified=False)
    deps.last_phase_stop = PhaseStop(
        role=role, reason=PhaseStopReason.BUDGET, tool_calls=40
    )
    return deps


def _unverified_status(deps: LeadDeps) -> str:
    return turn_record(run_context_for(deps)).facts.unverified


def _answer(prose: str, *, why: str = "") -> LeadResponse:
    return LeadResponse(prose=prose, strategy_changed=True, unverified_reason=why)


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


def test_a_reason_beside_a_recorded_stop_passes_on_the_first_answer() -> None:
    deps = _stopped()
    answer = _answer(_STATES_WHY, why=_WHY)

    assert hold_the_turn_contract(run_context_for(deps), answer) == answer
    markers = deps.state.turn_markers
    assert (markers.output_refusals, markers.unchecked_reply) == (0, False)


def test_the_reason_the_refusal_asks_for_passes_unmarked() -> None:
    deps = _stopped()
    with pytest.raises(ModelRetry) as raised:
        hold_the_turn_contract(run_context_for(deps), _answer(_STATES_WHY))

    hold_the_turn_contract(run_context_for(deps), _answer(_STATES_WHY, why=_WHY))

    assert _ASKED in str(raised.value)
    assert deps.state.turn_markers.unchecked_reply is False


@pytest.mark.parametrize("stopped", [None, "frame", "execution"])
def test_a_reason_with_no_stop_of_the_check_is_refused_then_marked(
    stopped: PhaseRole | None,
) -> None:
    deps = building_deps(verified=False) if stopped is None else _stopped(stopped)
    answer = _answer(_STATES_WHY, why=_WHY)
    with pytest.raises(ModelRetry) as raised:
        hold_the_turn_contract(run_context_for(deps), answer)

    assert hold_the_turn_contract(run_context_for(deps), answer) == answer
    assert _ASKED_TO_TRY in str(raised.value)
    assert deps.state.turn_markers.unchecked_reply is True


@pytest.mark.parametrize(
    ("prose", "why"),
    [(_STATES_WHY, ""), (_CLAIMS_A_CHECK, ""), (_CLAIMS_A_CHECK, "  ")],
)
def test_an_unacknowledged_unverified_build_is_refused_then_marked(
    prose: str, why: str
) -> None:
    deps = _stopped()
    answer = _answer(prose, why=why)
    with pytest.raises(ModelRetry):
        hold_the_turn_contract(run_context_for(deps), answer)

    assert hold_the_turn_contract(run_context_for(deps), answer) == answer
    assert deps.state.turn_markers.unchecked_reply is True


@pytest.mark.parametrize("sentence", _SAYS_VERIFIED)
def test_a_reply_that_says_verified_passes_beside_the_status(sentence: str) -> None:
    deps = _stopped()
    answer = _answer(f"{sentence} {_STATES_WHY}", why=_WHY)

    assert hold_the_turn_contract(run_context_for(deps), answer) == answer
    markers = deps.state.turn_markers
    assert (markers.output_refusals, markers.unchecked_reply) == (0, False)
    assert _unverified_status(deps) == UNVERIFIED_BUILD


def test_the_lead_sets_the_field_the_refusal_names() -> None:
    told: list[str] = []

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        request = messages[-1]
        if isinstance(request, ModelRequest):
            told.extend(
                p.model_response()
                for p in request.parts
                if isinstance(p, RetryPromptPart)
            )
        args = {"prose": _STATES_WHY, "strategyChanged": True}
        why = {"unverifiedReason": _WHY} if told else {}
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="final_result",
                    args=args | why,
                    tool_call_id=f"call_final_{len(told)}",
                )
            ]
        )

    deps = _stopped()
    result = asyncio.run(
        build_lead_agent().run(
            "Add an essentiality filter.",
            deps=deps,
            model=FunctionModel(_fn, model_name="scripted"),
        ),
    )

    assert result.output == _answer(_STATES_WHY, why=_WHY)
    assert [_ASKED in text for text in told] == [True]
    assert deps.state.turn_markers.unchecked_reply is False


def test_a_card_on_an_unverified_build_shows_the_status_and_passes_unmarked() -> None:
    deps = building_deps(verified=False)

    results = hold_the_contract_on_a_card(run_context_for(deps), _card(_STATES_WHY))

    assert results is None
    assert _unverified_status(deps) == UNVERIFIED_BUILD
    markers = deps.state.turn_markers
    assert (markers.output_refusals, markers.unchecked_reply) == (0, False)


@pytest.mark.parametrize("sentence", [*_SAYS_VERIFIED, _CLAIMS_A_CHECK])
def test_a_card_that_says_verified_passes_beside_the_status(sentence: str) -> None:
    deps = building_deps(verified=False)

    results = hold_the_contract_on_a_card(run_context_for(deps), _card(sentence))

    assert results is None
    markers = deps.state.turn_markers
    assert (markers.output_refusals, markers.unchecked_reply) == (0, False)
    assert _unverified_status(deps) == UNVERIFIED_BUILD


def test_a_turn_that_verified_shows_no_unverified_status() -> None:
    deps = building_deps(verified=True)

    assert _unverified_status(deps) == ""
