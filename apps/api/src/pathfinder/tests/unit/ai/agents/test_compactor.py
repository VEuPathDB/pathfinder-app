from __future__ import annotations

import pytest
from assistant_core.scratchpad.compactor import CompactionResult, CompactorDeps
from assistant_core.scratchpad.models import NoteCreate
from pydantic import ValidationError

from pathfinder.ai.agents.compactor import build_compactor_agent


def test_build_returns_agent_with_output_type() -> None:
    agent = build_compactor_agent(model_id=None)
    assert agent.output_type is CompactionResult


def test_compactor_deps_is_dataclass() -> None:
    deps = CompactorDeps(input_notes_markdown="stuff")
    assert deps.input_notes_markdown == "stuff"


def test_compaction_result_max_20_notes() -> None:
    with pytest.raises(ValidationError):
        CompactionResult(
            notes=[NoteCreate(title=f"t{i}", summary="s", body="b") for i in range(21)],
        )
