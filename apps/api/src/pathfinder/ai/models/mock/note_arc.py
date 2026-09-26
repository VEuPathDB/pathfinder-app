"""A FRAME pass that saves one note on what it bound and pins it before it answers."""

from __future__ import annotations

from assistant_core.models.scripted import TERMINAL_TOOL, scripted_call
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.arc import Script
from pathfinder.ai.models.mock.history import acted_tool_names
from pathfinder.ai.models.mock.reads import note_id

NOTE_TITLE = "Signal peptide and transmembrane intersection"
_NOTE = {
    "title": NOTE_TITLE,
    "summary": "The strategy intersects a signal peptide search and a membrane search.",
    "body": "Both searches run on the site organism; the INTERSECT keeps genes both return.",
}


def noted(script: Script) -> Script:
    """``script``, with a note saved and pinned before its answer."""

    def run(messages: list[ModelMessage]) -> ToolCallPart:
        call = script(messages)
        if call.tool_name != TERMINAL_TOOL:
            return call
        called = acted_tool_names(messages)
        if "note" not in called:
            return scripted_call("note", _NOTE)
        if "pin_note" not in called:
            return scripted_call("pin_note", {"note_id": note_id(messages) or ""})
        return call

    return run
