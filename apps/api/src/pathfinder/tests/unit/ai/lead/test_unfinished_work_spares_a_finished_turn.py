"""The unfinished-work rule over turns that did finish, on the Lead's real wiring."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    RetryPromptPart,
    ToolCallPart,
)
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.lead import edit_dispatch
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import CONTRACT_HEADING, LeadResponse
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_diff import SpecDiff
from pathfinder.tests.unit.ai.lead.conftest import (
    final_result_part,
    lead_deps,
    pipeline_state,
    tool_script_model,
    user_intent,
)

_A_FINISHED_REPLY = {
    "prose": "Step two keeps the genes whose text names a protease.",
    "nextState": "complete",
    "strategyChanged": False,
}


def _deps(prompt: str, classification: IntentClassification) -> LeadDeps:
    """A classified turn over a thread that holds a two-step strategy."""
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="screen", site_id="plasmodb")
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_root",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(id="step_a", search_name="GenesByTaxon"),
            secondary_input=StrategyStepNode(id="step_b", search_name="GenesByText"),
        )
    )
    graph.recompute_roots()
    session.graph = graph
    deps = lead_deps(
        pipeline_state(user_prompt=prompt, user_message_id=uuid4()),
        intent=user_intent(classification),
        strategy_session=session,
    )
    deps.state.turn_markers.intent_classified = True
    return deps


def _retry_prompts(messages: Sequence[ModelMessage]) -> list[str]:
    return [
        part.model_response()
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]


def _calls(messages: list[ModelMessage], tool_name: str) -> int:
    return sum(
        1
        for message in messages
        for part in message.parts
        if isinstance(part, ToolCallPart) and part.tool_name == tool_name
    )


def test_a_dispatch_refused_then_run_leaves_no_unfinished_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[str] = []

    async def _refused_once(**kwargs: Any) -> EditDelta:
        attempts.append(kwargs["reason"])
        if len(attempts) == 1:
            msg = "state the drop and call again"
            raise ModelRetry(msg)
        return EditDelta(diff=SpecDiff(), description="nothing to change")

    monkeypatch.setattr(edit_dispatch, "run_edit", _refused_once)

    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        if _calls(messages, "edit_strategy") < 2:
            return ToolCallPart(
                tool_name="edit_strategy",
                args={"reason": "tighten"},
                tool_call_id=uuid4().hex,
            )
        return final_result_part(_A_FINISHED_REPLY)

    deps = _deps("Tighten the screen.", IntentClassification.EDIT_STRATEGY)
    result = asyncio.run(
        build_lead_agent().run(
            deps.state.user_prompt, deps=deps, model=tool_script_model(_part)
        )
    )

    assert isinstance(result.output, LeadResponse)
    assert len(attempts) == 2
    assert [
        text
        for text in _retry_prompts(result.all_messages())
        if CONTRACT_HEADING in text
    ] == []


def test_one_unavailable_verification_leaves_a_finished_answer_alone() -> None:
    """A question turn offers no check, and its answer is still a whole answer."""

    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        if _calls(messages, "verify_strategy") < 1:
            return ToolCallPart(
                tool_name="verify_strategy",
                args={"reason": "check it"},
                tool_call_id=uuid4().hex,
            )
        return final_result_part(_A_FINISHED_REPLY)

    deps = _deps("What does step two ask?", IntentClassification.FOLLOW_UP_QUESTION)
    result = asyncio.run(
        build_lead_agent().run(
            deps.state.user_prompt, deps=deps, model=tool_script_model(_part)
        )
    )

    assert isinstance(result.output, LeadResponse)
    prompts = _retry_prompts(result.all_messages())
    assert [text for text in prompts if CONTRACT_HEADING in text] == []
