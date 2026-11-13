"""A turn that reaches its budget ends with a sentence that names it, and an
off-topic turn ends with its own reply whatever its requests spend."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
)
from pydantic_ai.models.function import (
    AgentInfo,
    DeltaThinkingCalls,
    DeltaThinkingPart,
    DeltaToolCall,
    DeltaToolCalls,
    FunctionModel,
)
from pydantic_ai.usage import UsageLimits
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy import StrategyStepNode

from strategist.ai.graph import _lead_model, lead_node
from strategist.ai.graph._lead_capture import LeadRunCapture
from strategist.ai.graph.lead_node import _drive_lead_stream
from strategist.ai.graph.runtime import Context
from strategist.ai.graph.state import PipelineState
from strategist.ai.lead import (
    evidence_card,
    sub_agent_dispatch,
    sub_agent_stream,
    sub_agent_tools,
)
from strategist.ai.lead.lead_agent import build_lead_agent
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.tools.toolsets import verification
from strategist.domain.site_checks import SiteCheck
from strategist.domain.strategy.build_outcome import BuildOutcome
from strategist.domain.strategy.constraints import ConstraintKind
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.session import StrategySession
from strategist.services.strategies.context import StrategyMutationContext
from strategist.tests._support.scripted_reading import read_as
from strategist.tests._support.site_checks import checked_site
from strategist.tests._support.sub_agents import pinned_sub_agent
from strategist.tests.unit.ai.graph._approval_turn import Collector, scripted_model
from strategist.tests.unit.ai.lead._budget_stop_turn import (
    ADDED_LINE,
    BUDGET,
    CHECKED_BUDGET,
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
from strategist.tests.unit.ai.lead.conftest import (
    called_tool_names,
    final_result_part,
)

_PROMPT = "Write me a Python script that reverses a linked list."
_ANSWER = "answered"
_BUILD_PROMPT = "Find Aedes genes up at 24 h against 18 h and 36 h."
# Each scripted request thinks this many words, so two requests spend what a
# production Lead request re-reads of its instructions.
_THOUGHT_WORDS = 30_000
_THOUGHT = " ".join(["word"] * _THOUGHT_WORDS)


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


def _read_then_answer() -> FunctionModel:
    """Read the ledger, then answer on the next request."""

    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        if "read_ledger_section" in called_tool_names(messages):
            return ToolCallPart(
                tool_name="final_result",
                args={
                    "prose": _ANSWER,
                    "nextState": "await_user",
                },
                tool_call_id="call_final",
            )
        return ToolCallPart(
            tool_name="read_ledger_section",
            args={"section": "frame"},
            tool_call_id="call_read",
        )

    return _thinking_model(_part)


def _thinking_model(part_for: Any) -> FunctionModel:
    """A scripted model whose every request thinks ``_THOUGHT`` before its call."""

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        return ModelResponse(parts=[part_for(messages)])

    async def _stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[DeltaThinkingCalls | DeltaToolCalls]:
        del info
        part: ToolCallPart = part_for(messages)
        yield {0: DeltaThinkingPart(content=_THOUGHT)}
        yield {
            1: DeltaToolCall(
                name=part.tool_name,
                json_args=part.args_as_json_str(),
                tool_call_id=part.tool_call_id,
            )
        }

    return FunctionModel(_fn, stream_function=_stream, model_name="scripted")


def _drive(
    monkeypatch: pytest.MonkeyPatch, classification: str
) -> tuple[LeadRunCapture, Collector]:
    read_as(monkeypatch, classification)
    model = _read_then_answer()
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: model)
    state = _state()
    capture = LeadRunCapture()
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


def test_an_off_topic_turn_ends_with_its_own_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Its read and its reply spend what any two Lead requests spend."""
    capture, writer = _drive(monkeypatch, "off_topic")

    assert capture.response is not None
    assert capture.response.prose == _ANSWER
    assert writer.chunks_of("error") == []


def test_the_turn_reports_what_its_run_spent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture, _ = _drive(monkeypatch, "off_topic")

    assert capture.tokens >= 2 * _THOUGHT_WORDS


def test_a_turn_stopped_at_its_budget_reports_what_its_run_spent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run that never reaches a result still spent its requests."""
    monkeypatch.setattr(
        lead_node, "lead_usage_limits", lambda: UsageLimits(request_limit=1)
    )
    capture, writer = _drive(monkeypatch, "follow_up_question")

    assert capture.response is not None
    assert capture.response.prose.endswith(
        BUDGET.replace("80 model calls", "1 model call")
    )
    assert capture.tokens >= _THOUGHT_WORDS
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
    """Build, verify; the budget ends the turn before a reply."""
    called = called_tool_names(messages)
    if "build_strategy" not in called:
        return ToolCallPart(
            tool_name="build_strategy", args={}, tool_call_id="call_build"
        )
    return ToolCallPart(
        tool_name="verify_strategy",
        args={"reason": "check the built step"},
        tool_call_id="call_verify",
    )


_OBJECTED = SiteCheck(
    kind=ConstraintKind.UNTYPED,
    subject="the reference group",
    status="fail",
    evidence=OBJECTION,
    requirement="other:the reference group",
)


def _objecting_verifier() -> FunctionModel:
    return scripted_model(
        lambda _messages: final_result_part(
            {"digest": objection().model_dump(by_alias=True, mode="json")}
        )
    )


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


def test_a_turn_at_its_whole_budget_reports_what_it_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The turn builds one step and sees it objected to, then spends its budget."""
    monkeypatch.setattr(
        lead_node, "lead_usage_limits", lambda: UsageLimits(request_limit=2)
    )
    read_as(monkeypatch, "extend_strategy")
    lead_model = scripted_model(_build_then_verify)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: lead_model)
    monkeypatch.setattr(sub_agent_tools, "get_mock_model", _objecting_verifier)
    checked_site(monkeypatch, [_OBJECTED])
    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _push)
    monkeypatch.setattr(
        sub_agent_dispatch, "import_gene_set_for_conversation", _no_gene_set
    )
    writer = Collector()
    for module in (sub_agent_dispatch, sub_agent_stream, evidence_card):
        monkeypatch.setattr(module, "get_stream_writer", lambda: writer)
    state = _framed_state()
    session = StrategySession(site_id=SITE_ID)
    capture = LeadRunCapture()
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
        [
            STRATEGY_LINE,
            ADDED_LINE,
            f"Verification objected: 'the reference group': {OBJECTION}",
            CHECKED_BUDGET.replace("80 model calls", "2 model calls"),
        ]
    )
