"""The one correction a reply that does not match its turn comes back with."""

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

from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.turn_contract import (
    CONTRACT_HEADING,
    LeadResponse,
    hold_the_turn_contract,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    ASKING_REPLY,
    CLEAN_REPLY,
    WITH_CODE,
    control_test_deps,
    framing_deps,
    off_topic_deps,
    open_frame_deps,
    reading_deps,
    reply,
)
from pathfinder.tests.unit.ai.lead.conftest import RetryRecordingScript


def _scripted_answer(prose: str) -> RetryRecordingScript:
    """A model that answers with this prose whatever it is told."""
    return RetryRecordingScript(
        ToolCallPart(
            tool_name="final_result",
            args={
                "prose": prose,
                "nextState": "await_user",
                "strategyChanged": False,
            },
            tool_call_id="call_final",
        ),
    )


class TestTheOneCorrection:
    def test_two_mismatches_are_listed_in_rule_order_under_one_heading(self) -> None:
        deps = open_frame_deps()
        deps.state.turn_markers.intent_classified = True
        report = reply(ASKING_REPLY, changed=True)

        with pytest.raises(ModelRetry) as raised:
            hold_the_turn_contract(run_context_for(deps), report)

        text = str(raised.value)
        assert text.startswith(CONTRACT_HEADING)
        assert "no build, edit, delete, clear or export" in text
        assert "question card (consult_user)" in text
        assert text.index("no build, edit, delete, clear or export") < text.index(
            "question card (consult_user)"
        )

    def test_the_second_answer_goes_through(self) -> None:
        deps = framing_deps()
        report = reply(ASKING_REPLY, changed=True)

        with pytest.raises(ModelRetry):
            hold_the_turn_contract(run_context_for(deps), report)

        assert deps.state.turn_markers.contract_refused is True
        assert hold_the_turn_contract(run_context_for(deps), report) is report

    def test_a_matching_reply_is_never_refused(self) -> None:
        deps = framing_deps()
        report = reply(CLEAN_REPLY)

        assert hold_the_turn_contract(run_context_for(deps), report) is report
        assert deps.state.turn_markers.contract_refused is False

    def test_a_deferred_request_is_not_prose(self) -> None:
        output = DeferredToolRequests()

        assert hold_the_turn_contract(run_context_for(reading_deps()), output) is (
            output
        )

    def test_the_contract_is_the_only_output_validator(self) -> None:
        agent = build_lead_agent()

        names = [v.function.__name__ for v in agent._output_validators]

        assert names == ["hold_the_turn_contract"]

    def test_written_counts_are_refused_until_the_reply_writes_none(self) -> None:
        answers = [
            "The strategy recovered 8 of 10 positive controls.",
            "It recovered 8 of them.",
            "It recovers most of your positive controls; the results stand beside.",
        ]
        retries: list[str] = []

        def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            del info
            request = messages[-1]
            if isinstance(request, ModelRequest):
                retries.extend(
                    p.model_response()
                    for p in request.parts
                    if isinstance(p, RetryPromptPart)
                )
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="final_result",
                        args={
                            "prose": answers[len(retries)],
                            "nextState": "await_user",
                            "strategyChanged": False,
                        },
                        tool_call_id=f"call_final_{len(retries)}",
                    )
                ]
            )

        result = asyncio.run(
            build_lead_agent().run(
                "How well does it recover my controls?",
                deps=control_test_deps(),
                model=FunctionModel(_fn, model_name="scripted"),
            ),
        )

        assert isinstance(result.output, LeadResponse)
        assert result.output.prose == answers[-1]
        assert [
            "- ``8``: no fact holds it, so take it out." in retry for retry in retries
        ] == [True, True]

    def test_an_out_of_scope_essay_is_re_asked_once_and_the_turn_answers(self) -> None:
        """The latch is the contract's, so every rule reaches the model once."""
        script = _scripted_answer(WITH_CODE)

        result = asyncio.run(
            build_lead_agent().run(
                "Write me a Python script that reverses a linked list.",
                deps=off_topic_deps(),
                model=script.model(),
            ),
        )

        assert isinstance(result.output, LeadResponse)
        assert result.output.prose == WITH_CODE
        assert len(script.retries) == 1
        assert "code" in script.retries[0]
