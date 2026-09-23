"""A generated title holds the thread's lock only for its local writes.

The WDK rename runs after the lock is released and is bounded, and the wait for
the lock is bounded, so neither can hold the turn's finish chunk open.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.persistence.repositories.conversation_strategy import (
    ConversationWithStrategy,
)
from pathfinder.persistence.repositories.conversation_update import (
    ConversationUpdate,
)
from pathfinder.services.conversations import turns
from pathfinder.services.conversations.turns import name_conversation_if_unnamed
from pathfinder.services.strategies import naming

_WDK_ID = 330679883
_TITLE = "Exported kinases in gametocytes"


@dataclass
class _Thread:
    """One unnamed thread holding a strategy WDK has, and its lock."""

    conversation: Conversation
    strategy: ConversationStrategyView
    locked: bool = False
    locked_at_wdk: list[bool] = field(default_factory=list)

    async def get_with_strategy(
        self, conversation_id: UUID, /
    ) -> ConversationWithStrategy | None:
        del conversation_id
        return self.conversation, self.strategy

    async def update_conversation(
        self, conversation_id: UUID, upd: ConversationUpdate, /
    ) -> None:
        del conversation_id
        if upd.name is not None:
            self.conversation.name = upd.name


def _thread() -> _Thread:
    now = datetime.now(UTC)
    return _Thread(
        conversation=Conversation(
            id=uuid4(),
            user_id=uuid4(),
            site_id="plasmodb",
            name="",
            created_at=now,
            updated_at=now,
        ),
        strategy=ConversationStrategyView(
            wdk_strategy_id=_WDK_ID,
            strategy_ast=StrategyAst(
                record_type="transcript",
                name="New Conversation",
                root=StrategyStepNode(id="step_a", search_name="GenesByTaxon"),
            ).model_dump(by_alias=True, exclude_none=True, mode="json"),
        ),
    )


class _HangingWDK:
    """A WDK that never answers a rename, recording whether the lock was held."""

    def __init__(self, thread: _Thread) -> None:
        self._thread = thread

    async def update_strategy(self, strategy_id: int, name: str | None = None) -> None:
        del strategy_id, name
        self._thread.locked_at_wdk.append(self._thread.locked)
        await asyncio.Event().wait()


def _install(monkeypatch: pytest.MonkeyPatch, thread: _Thread) -> None:
    @asynccontextmanager
    async def _lock(*_args: Any) -> AsyncIterator[None]:
        thread.locked = True
        try:
            yield None
        finally:
            thread.locked = False

    monkeypatch.setattr(turns, "strategy_write_lock", _lock)
    monkeypatch.setattr(turns, "ConversationRepository", lambda _session: thread)
    monkeypatch.setattr(naming, "get_strategy_api", lambda _site: _HangingWDK(thread))
    monkeypatch.setattr(naming, "WDK_RENAME_SECONDS", 0.05)


async def test_a_wdk_that_hangs_is_called_after_the_lock_and_left_at_the_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread()
    _install(monkeypatch, thread)

    written = await asyncio.wait_for(
        name_conversation_if_unnamed(thread.conversation.id, title=_TITLE), timeout=2
    )

    assert (written, thread.conversation.name, thread.locked_at_wdk) == (
        True,
        _TITLE,
        [False],
    )


async def test_a_lock_that_is_never_released_is_left_at_the_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _thread()
    _install(monkeypatch, thread)

    @asynccontextmanager
    async def _held_elsewhere(*_args: Any) -> AsyncIterator[None]:
        await asyncio.Event().wait()
        yield None

    monkeypatch.setattr(turns, "strategy_write_lock", _held_elsewhere)
    monkeypatch.setattr(turns, "LOCK_WAIT_SECONDS", 0.05)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            name_conversation_if_unnamed(thread.conversation.id, title=_TITLE),
            timeout=2,
        )
    assert thread.conversation.name == ""
