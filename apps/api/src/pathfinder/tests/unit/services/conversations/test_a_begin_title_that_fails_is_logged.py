"""A title /begin generates and cannot write is logged, never raised."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from pathfinder.services.conversations import begin


async def test_a_title_the_store_did_not_take_ends_the_task_quietly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: list[str] = []

    async def _title(_seed: str) -> str:
        return "Kinases in gametocytes"

    async def _fails(conversation_id: UUID, *, title: str) -> bool:
        del conversation_id
        written.append(title)
        raise TimeoutError

    monkeypatch.setattr(begin, "name_conversation_if_unnamed", _fails)

    await begin._persist_generated_title(uuid4(), "kinases", _title)

    assert written == ["Kinases in gametocytes"]
