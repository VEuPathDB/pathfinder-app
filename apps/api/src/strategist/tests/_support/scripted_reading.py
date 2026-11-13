"""A turn's reading stated by a test, in place of the reading the mock model scripts."""

from __future__ import annotations

import pytest

from strategist.ai.graph import _lead_reading
from strategist.ai.graph.state import PipelineState
from strategist.ai.lead.intent import UserIntent


def read_as(
    monkeypatch: pytest.MonkeyPatch, classification: str, **fields: object
) -> UserIntent:
    intent = UserIntent.model_validate(
        {
            "classification": classification,
            "inferredGoal": "the scripted goal",
            **fields,
        }
    )

    def _scripted(state: PipelineState, words: str) -> UserIntent:
        del state, words
        return intent

    monkeypatch.setattr(_lead_reading, "scripted_intent", _scripted)
    return intent
