"""The turn a build that read nothing takes, on the real Lead agent.

One classification, an answer the verification validator refuses, the check it
names, and one answer delivered.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from pathfinder.ai.lead import sub_agent_tools
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_agent import LeadResponse, build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.toolsets import verification
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    lead_deps,
    pipeline_state,
    session_with_one_step,
)

_ZERO_PROMPT = "Find ME49 genes with a signal peptide and a similar profile."
_ZERO_PROSE = "The strategy returned 0 genes, so here is one way to broaden it."
_ZERO_DIGEST = {
    "digest": {
        "disposition": "awaiting_user",
        "prose": "The root reads 0 records.",
        "reason": "The build is empty.",
        "success": False,
    },
}


class _VerifyingSubAgent:
    """The verification sub-agent, answering the digest of an empty build."""

    def model(self) -> FunctionModel:
        def _part() -> ToolCallPart:
            return ToolCallPart(
                tool_name="final_result",
                args=_ZERO_DIGEST,
                tool_call_id="call_digest",
            )

        def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            del messages, info
            return ModelResponse(parts=[_part()])

        async def _stream(
            messages: list[ModelMessage],
            info: AgentInfo,
        ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
            del messages, info
            part = _part()
            yield {
                0: DeltaToolCall(
                    name=part.tool_name,
                    json_args=part.args_as_json_str(),
                    tool_call_id=part.tool_call_id,
                ),
            }

        return FunctionModel(_fn, stream_function=_stream, model_name="scripted")


def _zero_build_deps() -> LeadDeps:
    """A turn whose build pushed one step and read nothing at the root."""
    state = pipeline_state(user_prompt=_ZERO_PROMPT, user_message_id=uuid4())
    state.record_build(BuildOutcome(pushed_step_ids=["step_a"], root_count=0))
    return lead_deps(state, strategy_session=session_with_one_step())


class _LeadJourney:
    """Classify, answer, and answer again after the refusal names the check."""

    def __init__(self) -> None:
        self.called: list[str] = []

    def model(self) -> FunctionModel:
        def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            del messages, info
            part = self._next()
            self.called.append(part.tool_name)
            return ModelResponse(parts=[part])

        return FunctionModel(_fn, model_name="scripted")

    def _next(self) -> ToolCallPart:
        if not self.called:
            return ToolCallPart(
                tool_name="classify_user_intent",
                args={
                    "intent": {
                        "classification": IntentClassification.NEW_STRATEGY.value,
                        "inferredGoal": "find the ME49 genes",
                    },
                },
                tool_call_id="call_classify",
            )
        if "verify_strategy" in self.called:
            return ToolCallPart(
                tool_name="final_result",
                args={"prose": _ZERO_PROSE, "nextState": "await_user"},
                tool_call_id="call_final_2",
            )
        if "final_result" in self.called:
            return ToolCallPart(
                tool_name="verify_strategy",
                args={"reason": "check the empty root"},
                tool_call_id="call_verify",
            )
        return ToolCallPart(
            tool_name="final_result",
            args={"prose": _ZERO_PROSE, "nextState": "await_user"},
            tool_call_id="call_final_1",
        )


async def test_a_build_at_zero_verifies_and_answers_once(
    monkeypatch: pytest.MonkeyPatch,
    collector: ChunkCollector,
) -> None:
    """The journey the incident took: one classification, one checked answer."""
    del collector
    deps = _zero_build_deps()
    journey = _LeadJourney()
    monkeypatch.setattr(sub_agent_tools, "get_mock_model", _VerifyingSubAgent().model)

    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[verification.build_toolset()],
        instructions="Follow the script.",
    ):
        result = await build_lead_agent().run(
            _ZERO_PROMPT,
            deps=deps,
            model=journey.model(),
        )

    assert isinstance(result.output, LeadResponse)
    assert result.output.prose == _ZERO_PROSE
    assert journey.called.count("classify_user_intent") == 1
    assert journey.called.count("final_result") == 2
    assert journey.called.count("verify_strategy") == 1
    assert deps.state.turn_markers.verification_dispatched is True
