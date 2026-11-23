from __future__ import annotations

import json

from assistant_core.scratchpad.compactor import MAX_COMPACTED_NOTES, CompactionResult
from assistant_core.scratchpad.models import NoteCreate
from pydantic_ai.messages import ModelMessage, TextPart

from strategist.ai.agents.compactor import INPUT_NOTES_HEADING
from strategist.ai.models.mock.reads import instructions_of

_BODY_LIMIT = 19_000


def compacts_the_notes(messages: list[ModelMessage]) -> bool:
    return INPUT_NOTES_HEADING in instructions_of(messages)


def _bodies(notes: str) -> list[str]:
    bodies = [""]
    for line in notes.splitlines():
        if len(bodies[-1]) + len(line) + 1 > _BODY_LIMIT:
            bodies.append("")
        bodies[-1] = f"{bodies[-1]}\n{line}" if bodies[-1] else line
    return [body for body in bodies if body.strip()]


def compaction(messages: list[ModelMessage]) -> TextPart:
    notes = instructions_of(messages).split(INPUT_NOTES_HEADING, 1)[1].strip()
    kept = CompactionResult(
        notes=[
            NoteCreate(
                title=f"Kept notes, part {index}",
                summary="Every input note, kept as written.",
                body=body,
            )
            for index, body in enumerate(_bodies(notes)[:MAX_COMPACTED_NOTES], 1)
        ]
    )
    return TextPart(json.dumps(kept.model_dump(by_alias=True, mode="json")))


__all__ = ["compaction", "compacts_the_notes"]
