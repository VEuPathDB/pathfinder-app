"""Each phase tool is on the Lead's list only when its precondition holds.

The classification is the turn's own, so a building intent from an earlier
message unlocks nothing. Every other precondition is read from the ledger, the
live graph and what this turn already did.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.intent_gate import BUILDING_TOOLS, UNCLASSIFIED_TOOLS
from pathfinder.ai.lead.lead_agent import LeadResponse, build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.build_outcome import BuildOutcome, StepPushFailure
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests.unit.ai.lead.conftest import (
    OfferedTools,
    lead_deps,
    pipeline_state,
    session_with_one_step,
    user_intent,
)

_PROSE = "Here is what I found."
_PROMPT = "Find A. gambiae midgut proteases"


# The research reads are served by a tool source, so an agent built without one
# offers neither.
_SERVED_TOOLS = frozenset({"research_web_search", "research_literature_search"})


def _session(*, with_steps: bool) -> StrategySession:
    if not with_steps:
        return StrategySession(site_id="plasmodb")
    return session_with_one_step()


def _deps(
    *,
    classification: IntentClassification | None = None,
    classified_this_turn: bool = True,
    domain: StrategyDomainState | None = None,
    with_steps: bool = False,
) -> LeadDeps:
    state = pipeline_state(
        user_prompt=_PROMPT,
        user_message_id=uuid4(),
        domain=domain,
    )
    intent = None if classification is None else user_intent(classification)
    if intent is not None and classified_this_turn:
        state.turn_markers.intent_classified = True
    return lead_deps(
        state,
        intent=intent,
        strategy_session=_session(with_steps=with_steps),
    )


def _final_only(seen: OfferedTools) -> FunctionModel:
    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        seen.record(info)
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="final_result",
                    args={"prose": _PROSE, "nextState": "await_user"},
                    tool_call_id="call_final",
                ),
            ],
        )

    return FunctionModel(_fn, model_name="scripted")


def _offered(deps: LeadDeps) -> frozenset[str]:
    seen = OfferedTools()
    result = asyncio.run(
        build_lead_agent().run(_PROMPT, deps=deps, model=_final_only(seen)),
    )
    assert isinstance(result.output, LeadResponse)
    return seen.steps[0]


def _spec_with_criteria() -> OperationalSpec:
    return OperationalSpec(
        goal="kinases",
        criteria=[Criterion(id="c1", text="kinases", search_name="GenesByText")],
    )


def _zero_build() -> BuildOutcome:
    return BuildOutcome(pushed_step_ids=["step_a"], zero_step_ids=["step_a"])


def _failed_build() -> BuildOutcome:
    return BuildOutcome(
        failed_steps=[
            StepPushFailure(
                step_id="step_a",
                search_name="GenesByTaxon",
                error="422 organism: Invalid value",
            ),
        ],
    )


def test_a_prior_turns_intent_does_not_unlock_this_turn() -> None:
    """A building classification carried over from an earlier message is stale."""
    offered = _offered(
        _deps(
            classification=IntentClassification.NEW_STRATEGY,
            classified_this_turn=False,
        ),
    )

    assert not (offered & BUILDING_TOOLS)
    assert "classify_user_intent" in offered


def test_an_unclassified_turn_reaches_only_the_always_on_tools() -> None:
    """The two served reads are absent: this turn resolved no research source."""
    assert _offered(_deps()) == UNCLASSIFIED_TOOLS - _SERVED_TOOLS


def test_a_classified_build_turn_reaches_frame_and_build() -> None:
    offered = _offered(_deps(classification=IntentClassification.NEW_STRATEGY))

    assert {"frame_problem", "build_strategy"} <= offered


def test_frame_is_hidden_once_a_frame_dispatch_ran_this_turn() -> None:
    deps = _deps(classification=IntentClassification.NEW_STRATEGY)
    deps.state.turn_markers.framed = True

    assert "frame_problem" not in _offered(deps)


def test_frame_is_hidden_for_an_edit_intent_over_existing_criteria() -> None:
    deps = _deps(
        classification=IntentClassification.EDIT_STRATEGY,
        domain=StrategyDomainState(operational_spec=_spec_with_criteria()),
        with_steps=True,
    )

    offered = _offered(deps)

    assert "frame_problem" not in offered
    assert "edit_strategy" in offered


def test_frame_is_offered_for_an_edit_intent_with_no_criteria_yet() -> None:
    deps = _deps(classification=IntentClassification.EDIT_STRATEGY)

    assert "frame_problem" in _offered(deps)


def test_frame_is_offered_when_an_edit_has_no_strategy_to_edit() -> None:
    """``edit_strategy`` refuses without steps and names ``frame_problem``."""
    deps = _deps(
        classification=IntentClassification.EDIT_STRATEGY,
        domain=StrategyDomainState(operational_spec=_spec_with_criteria()),
    )

    assert "frame_problem" in _offered(deps)


def test_frame_is_hidden_after_a_build_this_turn_returned_nothing() -> None:
    deps = _deps(
        classification=IntentClassification.NEW_STRATEGY,
        domain=StrategyDomainState(last_build_outcome=_zero_build()),
        with_steps=True,
    )
    deps.state.turn_markers.built = True

    assert "frame_problem" not in _offered(deps)


def test_a_new_message_reopens_frame_after_an_empty_build() -> None:
    """The zero result is answered by the user, and their answer re-frames."""
    deps = _deps(
        classification=IntentClassification.NEW_STRATEGY,
        domain=StrategyDomainState(last_build_outcome=_zero_build()),
    )

    assert "frame_problem" in _offered(deps)


def test_recovery_is_hidden_when_a_realized_build_read_zero() -> None:
    """A zero from a build whose every step pushed is a result, not a failure."""
    deps = _deps(
        classification=IntentClassification.NEW_STRATEGY,
        domain=StrategyDomainState(last_build_outcome=_zero_build()),
        with_steps=True,
    )

    assert "recover_failed_steps" not in _offered(deps)


def test_recovery_is_offered_when_a_step_failed_to_push() -> None:
    deps = _deps(
        classification=IntentClassification.NEW_STRATEGY,
        domain=StrategyDomainState(last_build_outcome=_failed_build()),
        with_steps=True,
    )

    assert "recover_failed_steps" in _offered(deps)


def test_build_is_hidden_when_the_strategy_already_has_steps() -> None:
    deps = _deps(
        classification=IntentClassification.EXTEND_STRATEGY,
        with_steps=True,
    )

    assert "build_strategy" not in _offered(deps)


def test_verify_is_hidden_until_something_is_built() -> None:
    deps = _deps(classification=IntentClassification.NEW_STRATEGY)

    assert "verify_strategy" not in _offered(deps)


def test_verify_is_offered_once_a_build_recorded_an_outcome() -> None:
    deps = _deps(
        classification=IntentClassification.NEW_STRATEGY,
        domain=StrategyDomainState(last_build_outcome=BuildOutcome()),
    )

    assert "verify_strategy" in _offered(deps)


def test_verify_is_offered_for_a_step_exported_without_a_build() -> None:
    """An EDA export leaves a real step and no build outcome."""
    deps = _deps(
        classification=IntentClassification.EXTEND_STRATEGY,
        with_steps=True,
    )

    assert "verify_strategy" in _offered(deps)


def test_verify_is_hidden_once_it_succeeded_this_turn() -> None:
    deps = _deps(
        classification=IntentClassification.NEW_STRATEGY,
        domain=StrategyDomainState(last_build_outcome=BuildOutcome()),
    )
    deps.state.turn_markers.verified = True

    assert "verify_strategy" not in _offered(deps)


def test_create_eda_step_is_hidden_until_a_preview_counted_the_subset() -> None:
    deps = _deps(classification=IntentClassification.EXTEND_STRATEGY)

    assert "create_eda_step" not in _offered(deps)


def test_create_eda_step_is_offered_after_a_preview_this_turn() -> None:
    deps = _deps(classification=IntentClassification.EXTEND_STRATEGY)
    deps.state.turn_markers.eda_previewed = True

    assert "create_eda_step" in _offered(deps)


def test_the_markers_belong_to_the_message_they_were_written_for() -> None:
    """The record rotates when the turn answers a different user message."""
    state = pipeline_state(user_message_id=UUID(int=1))
    state.turn_markers.intent_classified = True
    state.turn_markers.framed = True

    state.user_message_id = UUID(int=2)

    assert not state.turn_markers.intent_classified
    assert not state.turn_markers.framed
    assert state.turn_markers.message_id == UUID(int=2)


def _classify_args(classification: IntentClassification) -> dict[str, Any]:
    return {
        "intent": {
            "classification": classification.value,
            "inferredGoal": "what the user asked for",
        },
    }


def test_classifying_this_turn_marks_the_turn_and_unlocks_the_tools() -> None:
    """The degrade path: one classification, and the tools are back."""
    seen = OfferedTools()

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        if seen.record(info) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="classify_user_intent",
                        args=_classify_args(IntentClassification.NEW_STRATEGY),
                        tool_call_id="call_classify",
                    ),
                ],
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="final_result",
                    args={"prose": _PROSE, "nextState": "await_user"},
                    tool_call_id="call_final",
                ),
            ],
        )

    deps = _deps(
        classification=IntentClassification.FOLLOW_UP_QUESTION,
        classified_this_turn=False,
    )
    result = asyncio.run(
        build_lead_agent().run(
            _PROMPT,
            deps=deps,
            model=FunctionModel(_fn, model_name="scripted"),
        ),
    )

    assert isinstance(result.output, LeadResponse)
    assert seen.steps[0] == UNCLASSIFIED_TOOLS - _SERVED_TOOLS
    assert {"frame_problem", "build_strategy"} <= seen.steps[1]
    assert deps.state.turn_markers.intent_classified


def _replies_twice(seen: OfferedTools) -> FunctionModel:
    """A model that answers, is refused, and answers again."""

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        seen.record(info)
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="final_result",
                    args={"prose": _PROSE, "nextState": "await_user"},
                    tool_call_id=f"call_final_{len(seen.steps)}",
                ),
            ],
        )

    return FunctionModel(_fn, model_name="scripted")


def _unverified_build_deps() -> LeadDeps:
    deps = _deps(
        classification=IntentClassification.NEW_STRATEGY,
        domain=StrategyDomainState(last_build_outcome=_zero_build()),
        with_steps=True,
    )
    deps.state.turn_markers.built = True
    return deps


def test_a_refused_reply_leaves_verification_as_the_only_building_tool() -> None:
    """The turn built and never verified, so the retry offers one way on."""
    seen = OfferedTools()
    deps = _unverified_build_deps()

    result = asyncio.run(
        build_lead_agent().run(_PROMPT, deps=deps, model=_replies_twice(seen)),
    )

    assert isinstance(result.output, LeadResponse)
    assert seen.steps[1] & BUILDING_TOOLS == {"verify_strategy"}
