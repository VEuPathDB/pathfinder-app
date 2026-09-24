"""The mock classifies a build over a framed draft as extending it."""

from __future__ import annotations

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_pins import pinned_operational_spec
from pathfinder.ai.models.mock import arcs
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._answered_draft import framed
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_BUILD = "Find protein kinases in P. falciparum 3D7."
_CONSULT = "Consult me before planning this strategy."


def _pinned(spec: OperationalSpec | None) -> str:
    """The spec pin the Lead reads, as the agent renders it."""
    state = pipeline_state(domain=StrategyDomainState(operational_spec=spec))
    rendered = pinned_operational_spec(run_context_for(lead_deps(state)))
    assert rendered is not None
    return rendered


def _classification(messages: list[ModelMessage]) -> IntentClassification:
    head = arcs._lead_sequence(messages)[0]
    assert head.tool_name == "classify_user_intent"
    return UserIntent.model_validate(head.args_as_dict()["intent"]).classification


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (None, IntentClassification.NEW_STRATEGY),
        (framed(None), IntentClassification.EXTEND_STRATEGY),
    ],
    ids=["nothing_framed", "a_framed_draft"],
)
def test_a_build_request_extends_only_a_framed_draft(
    spec: OperationalSpec | None, expected: IntentClassification
) -> None:
    turn: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content=_BUILD)], instructions=_pinned(spec))
    ]

    assert _classification(turn) == expected


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (None, IntentClassification.NEW_STRATEGY),
        (framed(None), IntentClassification.EXTEND_STRATEGY),
    ],
    ids=["nothing_framed", "a_framed_draft"],
)
def test_a_resumed_consult_extends_only_a_framed_draft(
    spec: OperationalSpec | None, expected: IntentClassification
) -> None:
    turn: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content=_CONSULT)]),
        ModelResponse(
            parts=[ToolCallPart(tool_name="consult_user", args={}, tool_call_id="c1")]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="consult_user", content="answered", tool_call_id="c1"
                ),
                UserPromptPart(content="The user answered your questions: ..."),
            ],
            instructions=_pinned(spec),
        ),
    ]

    assert _classification(turn) == expected
