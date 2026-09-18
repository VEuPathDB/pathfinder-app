"""The steps a turn passes through before the model speaks, by name."""

from __future__ import annotations

from assistant_core.graph.stream_events import turn_status_event
from pydantic_ai.ui.vercel_ai.response_types import DataChunk

READING_THE_THREAD = "Reading the thread"
RECALLING_AND_READING = "Recalling earlier work and reading the thread"


def turn_step_status(label: str) -> DataChunk:
    """Say which step the turn is on. No model is waited on here."""
    return turn_status_event(label=label, waiting_on_llm=False)
