"""VERIFY reads the researcher's own words, not the classifier's paraphrase."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from pathfinder.ai.agents.strategy_instructions import pinned_ledger
from pathfinder.ai.agents.verification import (
    build_verification_agent,
    pinned_researcher_request,
)
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import sub_agent_tools
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import run_verification
from pathfinder.ai.tools.toolsets import verification
from pathfinder.tests._support.instructions import pinned_instructions
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.lead.conftest import (
    final_result_part,
    lead_deps,
    pipeline_state,
)
from pathfinder.tests.unit.domain.strategy._vaccine_request import VACCINE

pytestmark = pytest.mark.usefixtures("collector")

_HEADING = "## The researcher's request\n"
_PARAPHRASE = "blood-stage vaccine candidates"
_CLARIFICATION = "Use the merozoite stage only."
_PUSH_NAME = "push name: "


class _Instructions:
    """Answer at once, and keep the instructions the model was sent."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def _part(self, info: AgentInfo) -> ToolCallPart:
        self.sent.append(info.instructions or "")
        return final_result_part(
            {
                "digest": {
                    "disposition": "done",
                    "prose": "The strategy was not inspected.",
                    "reason": "Scripted answer.",
                    "success": False,
                },
            },
        )

    def model(self) -> FunctionModel:
        def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            del messages
            return ModelResponse(parts=[self._part(info)])

        async def _stream(
            messages: list[ModelMessage], info: AgentInfo
        ) -> AsyncIterator[dict[int, DeltaToolCall]]:
            del messages
            part = self._part(info)
            yield {
                0: DeltaToolCall(
                    name=part.tool_name,
                    json_args=part.args_as_json_str(),
                    tool_call_id=part.tool_call_id,
                ),
            }

        return FunctionModel(_fn, stream_function=_stream, model_name="scripted")


def _push_name(ctx: RunContext[AgentDeps]) -> str:
    return f"{_PUSH_NAME}{ctx.deps.user_prompt}"


def _classified(prompt: str) -> LeadDeps:
    deps = lead_deps(pipeline_state(user_prompt=prompt))
    classify_user_intent(
        run_context_for(deps, tool_call_id="call_classify"),
        UserIntent(
            classification=IntentClassification.NEW_STRATEGY,
            inferred_goal=_PARAPHRASE,
        ),
    )
    return deps


async def _verify_instructions(monkeypatch: pytest.MonkeyPatch, deps: LeadDeps) -> str:
    script = _Instructions()
    monkeypatch.setattr(sub_agent_tools, "get_mock_model", script.model)
    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[verification.build_toolset()],
        instructions=[pinned_researcher_request, pinned_ledger, _push_name],
    ):
        await run_verification(
            deps=deps,
            parent_tool_call_id="lead_call_verify",
            reason="check the vaccine candidates",
        )
    return script.sent[0]


def test_the_verification_agent_pins_the_researchers_request() -> None:
    assert "pinned_researcher_request" in pinned_instructions(
        build_verification_agent()
    )


async def test_verify_is_shown_the_request_under_its_own_heading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = await _verify_instructions(monkeypatch, _classified(VACCINE))

    assert sent.split(_HEADING)[1].split("\n\n")[0] == VACCINE
    assert "late schizonts or merozoites" in sent


async def test_the_paraphrase_is_labelled_as_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = await _verify_instructions(monkeypatch, _classified(VACCINE))

    intent_lines = [line for line in sent.splitlines() if line.startswith("- intent:")]

    assert intent_lines == [
        f"- intent: new_strategy; paraphrase, not the request: {_PARAPHRASE}"
    ]


async def test_a_clarification_is_judged_with_the_request_it_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _classified(VACCINE)
    deps.state.user_prompt = _CLARIFICATION

    sent = await _verify_instructions(monkeypatch, deps)

    assert sent.split(_HEADING)[1].startswith(
        f"{VACCINE}\n\nThe user then clarified: {_CLARIFICATION}"
    )


async def test_the_request_leaves_the_push_name_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _classified(VACCINE)
    deps.state.user_prompt = _CLARIFICATION

    sent = await _verify_instructions(monkeypatch, deps)

    assert sent.split(_PUSH_NAME)[1] == VACCINE
