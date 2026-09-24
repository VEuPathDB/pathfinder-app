"""A turn that reaches its budget ends with a sentence that names it.

The off-topic ceiling is lowered here so one scripted response passes it; what
the tests read is that the classification binds the rest of the run and that
the user gets a sentence instead of an exception.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.ai.graph import _lead_model, lead_node
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.lead_node import _drive_lead_stream
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead import (
    evidence_card,
    sub_agent_dispatch,
    sub_agent_stream,
    sub_agent_tools,
    turn_budget,
)
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.toolsets import verification
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.graph._approval_turn import Collector, scripted_model
from pathfinder.tests.unit.ai.lead._budget_stop_turn import (
    ADDED_LINE,
    BUDGET,
    OBJECTION,
    SEARCH,
    SITE_ID,
    STRATEGY_LINE,
    TITLE,
    WORDS,
    built_outcome,
    hold_the_built_step,
    objection,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    called_tool_names,
    final_result_part,
)

_PROMPT = "Write me a Python script that reverses a linked list."
_ANSWER = "answered"
_BUILD_PROMPT = "Find Aedes genes up at 24 h against 18 h and 36 h."
# Small enough that the first scripted response passes it.
_TINY_OFF_TOPIC_CAP = 5


def _quota_offline() -> AsyncSession:
    msg = "no database in this unit test"
    raise OperationalError(msg, None, Exception(msg))


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt=_PROMPT,
        user_message_id=uuid4(),
    )


def _deps(state: PipelineState, session: StrategySession | None = None) -> LeadDeps:
    return LeadDeps(
        state=state,
        intent=None,
        runtime=Context(
            site_id="plasmodb",
            user_id=state.user_id,
            strategy_session=session or StrategySession(site_id="plasmodb"),
            db_session_factory=_quota_offline,
            cancel_event=asyncio.Event(),
        ),
        retrieved_memories=[],
    )


def _classify_then_answer(classification: str) -> FunctionModel:
    """Classify the turn, then answer on the next request."""

    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        if "classify_user_intent" in called_tool_names(messages):
            return ToolCallPart(
                tool_name="final_result",
                args={
                    "prose": _ANSWER,
                    "nextState": "await_user",
                    "strategyChanged": False,
                },
                tool_call_id="call_final",
            )
        return ToolCallPart(
            tool_name="classify_user_intent",
            args={
                "intent": {
                    "classification": classification,
                    "inferredGoal": "write a linked list in Python",
                },
            },
            tool_call_id="call_classify",
        )

    return scripted_model(_part)


def _drive(
    monkeypatch: pytest.MonkeyPatch, classification: str
) -> tuple[_LeadRunCapture, Collector]:
    monkeypatch.setattr(turn_budget, "OFF_TOPIC_TURN_TOKEN_LIMIT", _TINY_OFF_TOPIC_CAP)
    model = _classify_then_answer(classification)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: model)
    state = _state()
    capture = _LeadRunCapture()
    writer = Collector()
    emitted: Any = writer
    asyncio.run(
        _drive_lead_stream(
            state=state,
            agent=build_lead_agent(),
            deps=_deps(state),
            capture=capture,
            writer=emitted,
            message_id=uuid4(),
        ),
    )
    return capture, writer


def test_an_off_topic_turn_stops_at_the_off_topic_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture, _ = _drive(monkeypatch, "off_topic")

    assert capture.response is not None
    assert capture.response.prose == (
        f"I stopped this turn at its budget of 80 model calls and "
        f"{_TINY_OFF_TOPIC_CAP} tokens. Narrow the request and send it again, "
        f"and I will start a fresh turn on it."
    )


def test_the_budget_stop_says_nothing_about_a_safety_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The user reads a budget, not an error chunk carrying the library's words."""
    capture, writer = _drive(monkeypatch, "off_topic")

    assert capture.response is not None
    assert "Exceeded the total_tokens_limit" not in capture.response.prose
    assert writer.chunks_of("error") == []


def test_a_question_about_the_data_keeps_the_whole_turn_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture, _ = _drive(monkeypatch, "follow_up_question")

    assert capture.response is not None
    assert capture.response.prose == _ANSWER


def _criterion() -> Criterion:
    return Criterion(
        id="c_up",
        text=WORDS,
        search_name=SEARCH,
        search_display_name=TITLE,
    )


def _framed_state() -> PipelineState:
    """A spec an earlier turn framed, ready for this turn to build."""
    state = _state()
    state.user_prompt = _BUILD_PROMPT
    state.domain.operational_spec = OperationalSpec(
        goal=_BUILD_PROMPT,
        criteria=[_criterion()],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="c_up")),
    )
    return state


def _build_then_verify(messages: list[ModelMessage]) -> ToolCallPart:
    """Classify, build, verify; the budget ends the turn before a reply."""
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
    return ToolCallPart(
        tool_name="verify_strategy",
        args={"reason": "check the built step"},
        tool_call_id="call_verify",
    )


def _objecting_verifier() -> FunctionModel:
    return scripted_model(
        lambda _messages: final_result_part(
            {"digest": objection().model_dump(by_alias=True, mode="json")}
        )
    )


async def _push(
    *, deps: StrategyMutationContext, root: StrategyStepNode
) -> BuildOutcome:
    hold_the_built_step(deps.strategy_session, root.id)
    return built_outcome(root.id)


async def _no_gene_set(**_kwargs: object) -> None:
    return None


def test_a_turn_at_its_whole_budget_reports_what_it_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The turn builds one step and sees it objected to, then spends its budget."""
    monkeypatch.setattr(
        lead_node, "lead_usage_limits", lambda: UsageLimits(request_limit=3)
    )
    lead_model = scripted_model(_build_then_verify)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: lead_model)
    monkeypatch.setattr(sub_agent_tools, "get_mock_model", _objecting_verifier)
    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _push)
    monkeypatch.setattr(
        sub_agent_dispatch, "import_gene_set_for_conversation", _no_gene_set
    )
    writer = Collector()
    for module in (sub_agent_dispatch, sub_agent_stream, evidence_card):
        monkeypatch.setattr(module, "get_stream_writer", lambda: writer)
    state = _framed_state()
    session = StrategySession(site_id=SITE_ID)
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
                deps=_deps(state, session),
                capture=capture,
                writer=emitted,
                message_id=uuid4(),
            ),
        )

    assert capture.response is not None
    assert capture.response.prose == "\n\n".join(
        [STRATEGY_LINE, ADDED_LINE, f"Verification objected: {OBJECTION}", BUDGET]
    )
