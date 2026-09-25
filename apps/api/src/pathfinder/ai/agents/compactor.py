from __future__ import annotations

from assistant_core.models.settings import build_model_settings
from assistant_core.scratchpad.compactor import (
    MAX_COMPACTED_NOTES,
    CompactionResult,
    CompactorDeps,
)
from pydantic_ai import Agent, RunContext

from pathfinder.ai.agents._model_resolution import (
    resolve_orchestrator_model_entry,
)
from pathfinder.ai.capabilities.metering import SpendMeter
from pathfinder.platform.model_keys import keyed_model

_COMPACTOR_INSTRUCTIONS = f"""\
You are compacting the notes kept for a researcher's conversation. Merge redundant notes, \
drop notes that have been superseded by later notes, and keep distinct \
findings intact. Preserve titles that are referenced elsewhere (tool \
outputs, sub-agent deltas) when possible. Return a new list of notes that \
replaces the input set. Output at most {MAX_COMPACTED_NOTES} notes.

Rules:
- Never invent content. Every output note must be grounded in at least one \
input note.
- Merge same-topic notes (same search name, same biological concept) into \
one note that captures what was learned, not the iterative path.
- Drop stale notes (e.g. "considering GenesByRNASeq" when a later note \
says "using GenesByRNASeq with params X").
- Keep dead-end notes - they prevent the agent re-trying known failures.
- Tags: preserve informative tags; drop housekeeping tags.
"""


def build_compactor_agent(
    *,
    meter: SpendMeter,
    model_id: str | None = None,
) -> Agent[CompactorDeps, CompactionResult]:
    """The compactor on the key that pays for its provider; ``meter`` records its runs."""
    entry = resolve_orchestrator_model_entry(model_id, None)
    agent: Agent[CompactorDeps, CompactionResult] = Agent(
        keyed_model(entry.id),
        deps_type=CompactorDeps,
        output_type=CompactionResult,
        instructions=_COMPACTOR_INSTRUCTIONS,
        model_settings=build_model_settings(entry.id),
        retries=2,
        name="compactor",
        defer_model_check=True,
        capabilities=[meter.on(entry.id)],
    )

    @agent.instructions
    def _input_notes(ctx: RunContext[CompactorDeps]) -> str:
        return (
            "## Input notes (non-pinned, for compaction)\n\n"
            f"{ctx.deps.input_notes_markdown}"
        )

    return agent
