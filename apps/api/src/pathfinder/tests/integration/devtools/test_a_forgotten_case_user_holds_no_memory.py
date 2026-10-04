"""A corpus case's user leaves no memory behind, and another user keeps theirs."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import MemoryStore

from pathfinder.devtools import eval_runner


async def _remember(store: MemoryStore, user_id: UUID) -> None:
    await store.put(
        user_id=user_id,
        value=MemoryValue(
            kind="preference",
            name="a preference",
            summary="answers in genes",
            tags=[],
            content={"note": "answers in genes"},
            created_at=datetime.now(UTC),
        ),
    )


async def test_a_forgotten_user_holds_no_memory(app_memory_store: MemoryStore) -> None:
    case_user, other_user = uuid4(), uuid4()
    await _remember(app_memory_store, case_user)
    await _remember(app_memory_store, other_user)

    await eval_runner.forget_user(case_user)

    held = [
        len(await app_memory_store.list_all(user_id=user, kind="preference"))
        for user in (case_user, other_user)
    ]
    assert held == [0, 1]
