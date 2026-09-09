from __future__ import annotations

from dataclasses import dataclass

from assistant_core.models.settings import build_model_settings
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from pydantic_ai import Agent, RunContext

from pathfinder.ai.agents._model_resolution import (
    resolve_orchestrator_model_entry,
)
from pathfinder.domain.scratchpad.models import NoteCreate


class CompactionResult(CamelModel):
    """Compactor's output — a new list of notes replacing the non-pinned set."""

    notes: list[NoteCreate] = Field(max_length=20)


@dataclass
class CompactorDeps:
    input_notes_markdown: str


_COMPACTOR_INSTRUCTIONS = """\
You are compacting a researcher's working notebook. Merge redundant notes, \
drop notes that have been superseded by later notes, and keep distinct \
findings intact. Preserve titles that are referenced elsewhere (tool \
outputs, sub-agent deltas) when possible. Return a new list of notes that \
replaces the input set. Output at most 20 notes.

Rules:
- Never invent content. Every output note must be grounded in at least one \
input note.
- Merge same-topic notes (same search name, same biological concept) into \
one note that captures what was learned, not the iterative path.
- Drop stale notes (e.g. "considering GenesByRNASeq" when a later note \
says "using GenesByRNASeq with params X").
- Keep dead-end notes — they prevent the agent re-trying known failures.
- Tags: preserve informative tags; drop housekeeping tags.
"""


def build_compactor_agent(
    *,
    model_id: str | None = None,
) -> Agent[CompactorDeps, CompactionResult]:
    entry = resolve_orchestrator_model_entry(model_id, None)
    agent: Agent[CompactorDeps, CompactionResult] = Agent(
        entry.id,
        deps_type=CompactorDeps,
        output_type=CompactionResult,
        instructions=_COMPACTOR_INSTRUCTIONS,
        model_settings=build_model_settings(entry.id),
        retries=2,
        name="compactor",
        defer_model_check=True,
    )

    @agent.instructions
    def _input_notes(ctx: RunContext[CompactorDeps]) -> str:
        return (
            "## Input notes (non-pinned, for compaction)\n\n"
            f"{ctx.deps.input_notes_markdown}"
        )

    return agent
