from __future__ import annotations

import pytest
from assistant_core.scratchpad.compactor import CompactionResult, CompactorDeps
from assistant_core.scratchpad.models import NoteCreate
from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.ai.agents.compactor import build_compactor_agent
from pathfinder.ai.capabilities.metering import SpendMeter


def test_build_returns_agent_with_output_type() -> None:
    agent = build_compactor_agent(meter=SpendMeter(), model_id=None)
    assert agent.output_type is CompactionResult


def test_compactor_deps_is_dataclass() -> None:
    deps = CompactorDeps(input_notes_markdown="stuff")
    assert deps.input_notes_markdown == "stuff"


def test_compaction_result_max_20_notes() -> None:
    with pytest.raises(ValidationError):
        CompactionResult(
            notes=[NoteCreate(title=f"t{i}", summary="s", body="b") for i in range(21)],
        )


_INPUT_NOTES = """\
### [n-f89a62] Verified signal peptide or transmembrane strategy
summary: The UNION returned 1,203 records from GenesWithSignalPeptide (479) and \
GenesByTransmembraneDomains (840).

Root step 440877253. Controls: PF3D7_0100600 and PF3D7_0101300 positive; \
PF3D7_1246200 negative.
"""
_EVERY_FACT = (
    "GenesWithSignalPeptide (479) and GenesByTransmembraneDomains (840) give a "
    "UNION of 1203 records at root step 440877253. Positive controls PF3D7_0100600 "
    "and PF3D7_0101300; negative control PF3D7_1246200."
)
_WITHOUT_ONE_GENE = _EVERY_FACT.replace(" and PF3D7_0101300", "")


class _Answers:
    """Answers each compactor request with the next body and keeps what it was sent."""

    def __init__(self, *bodies: str) -> None:
        self._bodies = list(bodies)
        self.requests: list[list[ModelMessage]] = []
        self.instructions: list[str | None] = []

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.requests.append(messages)
        self.instructions.append(info.instructions)
        body = self._bodies[min(len(self.requests), len(self._bodies)) - 1]
        note = {"title": "signal peptide union", "summary": "merged", "body": body}
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"notes": [note]})]
        )

    def retry_prompts(self) -> list[str]:
        return [
            str(part.content)
            for messages in self.requests
            for message in messages[-1:]
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, RetryPromptPart)
        ]


async def _compact(answers: _Answers, notes: str = _INPUT_NOTES) -> CompactionResult:
    agent = build_compactor_agent(meter=SpendMeter(), model_id=None)
    with agent.override(model=FunctionModel(answers)):
        result = await agent.run(
            "Compact the notebook.", deps=CompactorDeps(input_notes_markdown=notes)
        )
    return result.output


async def test_a_compaction_that_keeps_every_identifier_is_accepted() -> None:
    answers = _Answers(_EVERY_FACT)

    output = await _compact(answers)

    assert [note.body for note in output.notes] == [_EVERY_FACT]
    assert len(answers.requests) == 1


async def test_a_compaction_that_drops_a_gene_id_is_retried_naming_it() -> None:
    answers = _Answers(_WITHOUT_ONE_GENE, _EVERY_FACT)

    output = await _compact(answers)

    assert [note.body for note in output.notes] == [_EVERY_FACT]
    assert len(answers.requests) == 2
    assert answers.retry_prompts() == [
        (
            "The compacted notes dropped 1 identifier the input notes carry. Every "
            "gene id, step id, strategy id, search name and count in the input must "
            "appear verbatim in the output. Missing: PF3D7_0101300"
        )
    ]


async def test_a_compaction_that_keeps_dropping_fails_after_three_attempts() -> None:
    answers = _Answers(_WITHOUT_ONE_GENE)

    with pytest.raises(UnexpectedModelBehavior):
        await _compact(answers)

    assert len(answers.requests) == 3


async def test_the_retry_lists_twenty_missing_identifiers_then_a_count() -> None:
    genes = [f"PF3D7_01{index:05d}" for index in range(25)]
    answers = _Answers("nothing kept", " ".join(genes))

    await _compact(
        answers, notes=f"### [n-a] genes\nsummary: list\n\n{' '.join(genes)}"
    )

    (prompt,) = answers.retry_prompts()
    assert prompt.startswith("The compacted notes dropped 25 identifiers")
    assert prompt.endswith(f"Missing: {', '.join(sorted(genes)[:20])} and 5 more")


async def test_the_instructions_state_that_every_identifier_is_kept() -> None:
    answers = _Answers(_EVERY_FACT)

    await _compact(answers)

    (instructions,) = answers.instructions
    assert (
        "- Every gene id, step id, strategy id, search name and count in the input "
        "appears verbatim in the output.\n"
    ) in (instructions or "")
