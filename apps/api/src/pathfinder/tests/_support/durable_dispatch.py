"""What a durable tool's call writes, captured without a database or a queue."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.tasks import decorator


class _Task:
    def __init__(self, deferred: list[dict[str, Any]]) -> None:
        self._deferred = deferred

    async def defer_async(self, **payload: Any) -> None:
        self._deferred.append(payload)


class _App:
    def __init__(self, deferred: list[dict[str, Any]]) -> None:
        self._deferred = deferred

    def configure_task(self, *, name: str, queue: str, lock: str) -> _Task:
        del name, queue, lock
        return _Task(self._deferred)


@dataclass(slots=True)
class DurableDispatch:
    """The task rows a call created, and the jobs it deferred."""

    created: list[dict[str, Any]] = field(default_factory=list)
    deferred: list[dict[str, Any]] = field(default_factory=list)


def capture_durable_dispatch(monkeypatch: pytest.MonkeyPatch) -> DurableDispatch:
    """Record what the durable decorator creates and defers."""
    dispatch = DurableDispatch()

    async def create(**kwargs: Any) -> UUID:
        dispatch.created.append(dict(kwargs))
        return uuid4()

    monkeypatch.setattr(decorator, "create_background_task", create)
    monkeypatch.setattr(decorator, "task_app", lambda: _App(dispatch.deferred))
    monkeypatch.setattr(decorator, "get_stream_writer", lambda: lambda _payload: None)
    return dispatch
