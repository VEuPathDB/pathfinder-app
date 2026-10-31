"""The one correction a reply that does not match its turn comes back with."""

from __future__ import annotations

import asyncio

import pytest
from pydantic_ai import DeferredToolRequests
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import (
    ToolCallPart,
)

from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.turn_contract import (
    CONTRACT_HEADING,
    LeadResponse,
    hold_the_turn_contract,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    AN_ESSAY,
    ASKING_REPLY,
    CLEAN_REPLY,
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
            },
            tool_call_id="call_final",
        ),
    )


class TestTheOneCorrection:
    def test_a_mismatch_is_listed_under_the_one_heading(self) -> None:
        deps = open_frame_deps()
        deps.state.turn_markers.intent_classified = True
        report = reply(f"It keeps 12 genes. {ASKING_REPLY}")

        with pytest.raises(ModelRetry) as raised:
            hold_the_turn_contract(run_context_for(deps), report)

        text = str(raised.value)
        assert (text.startswith(CONTRACT_HEADING), "``12``" in text) == (True, False)
        assert "question card (consult_user)" in text

    def test_the_second_answer_goes_through(self) -> None:
        deps = open_frame_deps()
        deps.state.turn_markers.intent_classified = True
        report = reply(ASKING_REPLY)

        with pytest.raises(ModelRetry):
            hold_the_turn_contract(run_context_for(deps), report)

        assert deps.state.turn_markers.contract_refused is True
        assert hold_the_turn_contract(run_context_for(deps), report) == reply(
            ASKING_REPLY
        )
        assert deps.state.turn_markers.unchecked_reply is True

    def test_a_matching_reply_is_never_refused(self) -> None:
        deps = framing_deps()
        report = reply(CLEAN_REPLY)

        assert hold_the_turn_contract(run_context_for(deps), report) == report
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

    def test_an_out_of_scope_essay_is_re_asked_once_and_the_turn_answers(self) -> None:
        """The latch is the contract's, so every rule reaches the model once."""
        script = _scripted_answer(AN_ESSAY)

        result = asyncio.run(
            build_lead_agent().run(
                "Write me a Python script that reverses a linked list.",
                deps=off_topic_deps(),
                model=script.model(),
            ),
        )

        assert isinstance(result.output, LeadResponse)
        assert result.output.prose == AN_ESSAY
        assert len(script.retries) == 1
        assert "400 characters" in script.retries[0]
