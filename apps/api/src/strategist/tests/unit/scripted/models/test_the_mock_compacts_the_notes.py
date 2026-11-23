from __future__ import annotations

from assistant_core.scratchpad.compactor import CompactorDeps

from strategist.ai.agents.compactor import build_compactor_agent
from strategist.ai.capabilities.metering import SpendMeter
from strategist.domain.scratchpad_facts import hard_facts
from strategist_scripted.models import get_mock_model

_NOTES = "\n\n".join(
    f"### [n-{index:03d}] kinase finding {index}\nsummary: a finding\n\n"
    f"PF3D7_01{index:05d} is held by step {440877000 + index} in GenesByTaxon."
    for index in range(60)
)


async def test_a_mock_compaction_keeps_every_identifier_in_one_answer() -> None:
    agent = build_compactor_agent(meter=SpendMeter(), model_id=None)

    with agent.override(model=get_mock_model()):
        result = await agent.run(
            "Compact the notebook.", deps=CompactorDeps(input_notes_markdown=_NOTES)
        )

    kept = "\n".join(note.body for note in result.output.notes)
    assert (hard_facts(_NOTES) - hard_facts(kept), result.usage().requests) == (
        frozenset(),
        1,
    )
