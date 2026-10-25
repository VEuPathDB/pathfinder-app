from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_facts import show_the_facts
from pathfinder.ai.graph._lead_stops import final_reply, strategy_change
from pathfinder.ai.graph.lead_node import _drive_lead_stream
from pathfinder.ai.lead import (
    evidence_card,
    sub_agent_dispatch,
    sub_agent_stream,
    sub_agent_tools,
)
from pathfinder.ai.lead.deltas import VerificationStopped
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.phase_stop import PhaseStopReason
from pathfinder.ai.tools.toolsets import verification
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.domain.turn_facts import UNVERIFIED_BUILD, TurnFacts
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.graph._approval_turn import Collector, scripted_model
from pathfinder.tests.unit.ai.graph.test_lead_turn_budget import _deps, _framed_state
from pathfinder.tests.unit.ai.lead._budget_stop_turn import (
    SITE_ID,
    built_outcome,
    hold_the_built_step,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    called_tool_names,
    final_result_part,
)

_REPLY = (
    "I added the step. The verification pass stopped before it finished, so "
    "the new step is not checked yet."
)

_UNWRITTEN = (
    "I could not write the answer to this turn. The change shown beside this "
    "reply landed and was not checked. Ask me to check it and I will go on "
    "from there."
)


def _build_verify_then_reply(messages: list[ModelMessage]) -> ToolCallPart:
    called = called_tool_names(messages)
    if "classify_user_intent" not in called:
        return ToolCallPart(
            tool_name="classify_user_intent",
            args={
                "intent": {
                    "classification": "extend_strategy",
                    "inferredGoal": "genes up at 24 h",
                },
            },
            tool_call_id="call_classify",
        )
    if "build_strategy" not in called:
        return ToolCallPart(
            tool_name="build_strategy", args={}, tool_call_id="call_build"
        )
    if "verify_strategy" not in called:
        return ToolCallPart(
            tool_name="verify_strategy",
            args={"reason": "check the built step"},
            tool_call_id="call_verify",
        )
    return final_result_part(
        {
            "prose": _REPLY,
            "nextState": "await_user",
            "strategyChanged": True,
            "unverifiedReason": "the verification pass stopped before it finished",
        }
    )


def _build_then_reply_out_of_shape(messages: list[ModelMessage]) -> ToolCallPart:
    if "build_strategy" not in called_tool_names(messages):
        return _build_verify_then_reply(messages)
    return final_result_part({"prose": _REPLY, "nextState": "await_user"})


def _misshapen_verifier() -> Any:
    return scripted_model(lambda _messages: final_result_part({"digest": {}}))


async def _push(
    *,
    deps: StrategyMutationContext,
    root: StrategyStepNode,
    description: str | None = None,
) -> BuildOutcome:
    hold_the_built_step(deps.strategy_session, root.id)
    return built_outcome(root.id)


async def _no_gene_set(**_kwargs: object) -> None:
    return None


def _verify_returns(messages: list[ModelMessage]) -> list[object]:
    return [
        part.content
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "verify_strategy"
    ]


def test_a_check_whose_answer_is_out_of_shape_ends_in_the_leads_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead_model = scripted_model(_build_verify_then_reply)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: lead_model)
    monkeypatch.setattr(sub_agent_tools, "get_mock_model", _misshapen_verifier)
    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _push)
    monkeypatch.setattr(
        sub_agent_dispatch, "import_gene_set_for_conversation", _no_gene_set
    )
    writer = Collector()
    for module in (sub_agent_dispatch, sub_agent_stream, evidence_card):
        monkeypatch.setattr(module, "get_stream_writer", lambda: writer)
    state = _framed_state()
    deps = _deps(state, StrategySession(site_id=SITE_ID))
    capture = _LeadRunCapture()
    emitted: Any = writer
    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[verification.build_toolset()],
        instructions="Follow the script.",
    ):
        asyncio.run(
            _drive_lead_stream(
                state=state,
                agent=build_lead_agent(),
                deps=deps,
                capture=capture,
                writer=emitted,
                message_id=uuid4(),
            ),
        )

    assert capture.run_error is None
    assert capture.response is not None
    assert capture.response.prose == _REPLY
    assert writer.chunks_of("error") == []
    markers = deps.state.turn_markers
    assert (markers.output_refusals, markers.unchecked_reply) == (0, False)
    assert markers.build_unverified is True
    stop = deps.last_phase_stop
    assert stop is not None
    assert (stop.role, stop.reason) == (
        "verification",
        PhaseStopReason.OUTPUT_RETRIES,
    )
    assert [
        VerificationStopped.model_validate(content).stop
        for content in _verify_returns(capture.new_messages)
    ] == [stop]


def test_a_reply_out_of_shape_every_time_ends_on_the_turns_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead_model = scripted_model(_build_then_reply_out_of_shape)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: lead_model)
    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _push)
    monkeypatch.setattr(
        sub_agent_dispatch, "import_gene_set_for_conversation", _no_gene_set
    )
    writer = Collector()
    for module in (sub_agent_dispatch, sub_agent_stream, evidence_card):
        monkeypatch.setattr(module, "get_stream_writer", lambda: writer)
    state = _framed_state()
    deps = _deps(state, StrategySession(site_id=SITE_ID))
    capture = _LeadRunCapture()
    emitted: Any = writer
    asyncio.run(
        _drive_lead_stream(
            state=state,
            agent=build_lead_agent(),
            deps=deps,
            capture=capture,
            writer=emitted,
            message_id=uuid4(),
        ),
    )
    reply = final_reply(
        capture, deps.unanswered_stage, change=strategy_change(deps.state)
    )
    capture.response = reply
    show_the_facts(emitted, deps, capture)

    assert capture.run_error is None
    assert writer.chunks_of("error") == []
    assert reply is not None
    assert (reply.prose, reply.strategy_changed) == (_UNWRITTEN, True)
    (shown,) = [chunk["data"] for chunk in writer.chunks_of("data-facts")]
    facts = TurnFacts.model_validate(shown)
    assert facts.unverified == UNVERIFIED_BUILD
    assert facts.refusal == ""
    assert ([step.count for step in facts.steps], facts.root_count) == ([70], 70)


_EMPTY = "Received empty model response"


def _empty(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del messages, info
    raise UnexpectedModelBehavior(_EMPTY)


async def _empty_streamed(
    messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[str]:
    del messages, info
    raise UnexpectedModelBehavior(_EMPTY)
    yield ""


def test_another_model_fault_of_the_lead_ends_on_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead_model = FunctionModel(
        _empty, stream_function=_empty_streamed, model_name="scripted"
    )
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: lead_model)
    writer = Collector()
    state = _framed_state()
    deps = _deps(state, StrategySession(site_id=SITE_ID))
    capture = _LeadRunCapture()
    emitted: Any = writer
    asyncio.run(
        _drive_lead_stream(
            state=state,
            agent=build_lead_agent(),
            deps=deps,
            capture=capture,
            writer=emitted,
            message_id=uuid4(),
        ),
    )
    reply = final_reply(
        capture, deps.unanswered_stage, change=strategy_change(deps.state)
    )

    assert capture.run_error == _EMPTY
    assert [chunk["errorText"] for chunk in writer.chunks_of("error")] == [_EMPTY]
    assert reply is not None
    assert reply.prose.startswith(
        "I stopped this turn on an error I could not recover from; what it "
        "answered is shown beside this reply."
    )
