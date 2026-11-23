from __future__ import annotations

from assistant_core.scratchpad.compactor import CompactorDeps
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from strategist.ai.agents.compactor import build_compactor_agent
from strategist.ai.capabilities.metering import SpendMeter
from strategist.tests._support.native_answers import answered, feedback

_GENES = [f"PF3D7_01{index:05d}" for index in range(70)]


class _Compactor:
    def __init__(self) -> None:
        self.told: list[str] = []

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        self.told.extend(feedback(messages[-1:]))
        body = " ".join(_GENES) if self.told else "nothing kept"
        note = {"title": "genes", "summary": "list", "body": body}
        return ModelResponse(parts=[answered({"notes": [note]})])


async def test_a_compaction_that_drops_seventy_identifiers_names_all_seventy() -> None:
    compactor = _Compactor()
    agent = build_compactor_agent(meter=SpendMeter(), model_id=None)
    notes = f"### [n-a] genes\nsummary: list\n\n{' '.join(_GENES)}"

    with agent.override(model=FunctionModel(compactor)):
        await agent.run("Compact.", deps=CompactorDeps(input_notes_markdown=notes))

    [told] = compactor.told
    assert "The compacted notes dropped 70 identifiers" in told
    assert f"Missing: {', '.join(sorted(_GENES))}" in told
