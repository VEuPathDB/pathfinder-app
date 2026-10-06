from __future__ import annotations

import time
from collections.abc import Awaitable

from cachetools import LRUCache

SLOW_COUNT_SECONDS = 10.0

_SLOW_SEARCHES: LRUCache[tuple[str, str], bool] = LRUCache(maxsize=512)


def counts_slowly(site_id: str, search_name: str) -> bool:
    return (site_id, search_name) in _SLOW_SEARCHES


async def timed[T](site_id: str, search_name: str, count: Awaitable[T]) -> T:
    start = time.monotonic()
    try:
        return await count
    finally:
        if time.monotonic() - start >= SLOW_COUNT_SECONDS:
            _SLOW_SEARCHES[(site_id, search_name)] = True
