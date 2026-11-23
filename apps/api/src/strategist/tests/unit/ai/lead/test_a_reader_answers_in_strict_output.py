from __future__ import annotations

import pytest
from assistant_core.scratchpad.compactor import CompactionResult, CompactorDeps
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.profiles.openai import OpenAIJsonSchemaTransformer

from strategist.ai.agents.compactor import build_compactor_agent
from strategist.ai.audit.synthesis import SynthesisDeps, build_synthesis_agent
from strategist.ai.capabilities.metering import SpendMeter
from strategist.ai.lead.message_reader import ReaderInput, _ModelReading, read_message
from strategist.domain.audit.verdicts import SynthesisDraft
from strategist.domain.message_reading import StatedRequest


class _AskedError(Exception):
    pass


class _Seen:
    def __init__(self) -> None:
        self.asked: list[ModelRequestParameters] = []

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        self.asked.append(info.model_request_parameters)
        raise _AskedError


def _strict(seen: _Seen) -> list[tuple[str, bool | None]]:
    return [
        (p.output_mode, None if p.output_object is None else p.output_object.strict)
        for p in seen.asked
    ]


async def _undecided(request: object) -> None:
    del request


async def test_both_readers_ask_for_strict_native_output() -> None:
    seen = _Seen()

    with pytest.raises(_AskedError):
        await read_message(
            ReaderInput(conversation="", strategy="", message="kinases"),
            model=FunctionModel(seen),
            model_id="openai:gpt-5.6-luna",
            meter=SpendMeter(),
            ask=_undecided,
        )

    assert _strict(seen) == [("native", True), ("native", True)]


async def test_the_compactor_asks_for_strict_native_output() -> None:
    seen = _Seen()
    agent = build_compactor_agent(meter=SpendMeter(), model_id=None)

    with agent.override(model=FunctionModel(seen)), pytest.raises(_AskedError):
        await agent.run("Compact.", deps=CompactorDeps(input_notes_markdown=""))

    assert _strict(seen) == [("native", True)]


async def test_the_synthesis_asks_for_strict_native_output() -> None:
    seen = _Seen()
    agent: Agent[SynthesisDeps, object] = build_synthesis_agent()

    with agent.override(model=FunctionModel(seen)), pytest.raises(_AskedError):
        await agent.run("Synthesize.", deps=SynthesisDeps(kept={}))

    assert _strict(seen) == [("native", True)]


@pytest.mark.parametrize(
    "output", [StatedRequest, _ModelReading, CompactionResult, SynthesisDraft]
)
def test_each_strict_output_schema_is_strict_on_openai(output: type[BaseModel]) -> None:
    walked = OpenAIJsonSchemaTransformer(output.model_json_schema(), strict=True)
    walked.walk()

    assert walked.is_strict_compatible is True


def test_an_organism_given_as_an_object_is_no_stated_request() -> None:
    with pytest.raises(ValidationError, match="organism"):
        StatedRequest.model_validate(
            {
                "requirements": [
                    {
                        "quote": "Plasmodium falciparum",
                        "kind": "organism",
                        "organism": {"organism": "Plasmodium falciparum"},
                        "hard": True,
                    }
                ]
            }
        )
