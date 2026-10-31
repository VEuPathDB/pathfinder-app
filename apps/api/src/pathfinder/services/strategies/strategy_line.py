from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from weakref import WeakValueDictionary

from assistant_core.platform.db import DBSessionFactory
from sqlalchemy import text

type StrategyLine = Callable[[str, int], AbstractAsyncContextManager[None]]

_TAKE = text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))")


def _key(site_id: str, wdk_strategy_id: int) -> str:
    return f"wdk-strategy:{site_id}:{wdk_strategy_id}"


class _InProcessLine:
    def __init__(self) -> None:
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    @asynccontextmanager
    async def __call__(self, site_id: str, wdk_strategy_id: int) -> AsyncIterator[None]:
        key = _key(site_id, wdk_strategy_id)
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        async with lock:
            yield


def postgres_strategy_line(session_factory: DBSessionFactory) -> StrategyLine:
    @asynccontextmanager
    async def hold(site_id: str, wdk_strategy_id: int) -> AsyncIterator[None]:
        async with session_factory() as session:
            await session.execute(_TAKE, {"k": _key(site_id, wdk_strategy_id)})
            yield
            await session.commit()

    return hold


class _Installed:
    line: StrategyLine = _InProcessLine()


def use_strategy_line(line: StrategyLine) -> StrategyLine:
    previous = _Installed.line
    _Installed.line = line
    return previous


def held_strategy(
    site_id: str, wdk_strategy_id: int
) -> AbstractAsyncContextManager[None]:
    return _Installed.line(site_id, wdk_strategy_id)
