"""A unit of audit work counts the WDK requests the client reported inside it."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from veupathdb import NoObserver, get_observer, set_observer

from pathfinder.platform.metrics import PathfinderObserver, counting_wdk_requests

_ATTRS = {
    "method": "POST",
    "endpoint_group": "users",
    "site_host": "qa.plasmodb.org",
    "has_auth": "true",
    "status_family": "2xx",
    "outcome": "ok",
}


@pytest.fixture(autouse=True)
def observed() -> Iterator[None]:
    set_observer(PathfinderObserver())
    try:
        yield
    finally:
        set_observer(NoObserver())


def test_requests_inside_the_block_are_counted() -> None:
    get_observer().on_wdk_request(0.01, _ATTRS)
    with counting_wdk_requests() as tally:
        get_observer().on_wdk_request(0.01, _ATTRS)
        get_observer().on_wdk_request(0.02, _ATTRS)
    get_observer().on_wdk_request(0.01, _ATTRS)
    assert tally.count == 2


async def test_a_task_the_block_spawns_counts_into_it() -> None:
    async def read() -> None:
        get_observer().on_wdk_request(0.01, _ATTRS)

    with counting_wdk_requests() as tally:
        await asyncio.gather(read(), read(), read())
    assert tally.count == 3


async def test_a_thread_the_block_starts_counts_into_it() -> None:
    def read() -> None:
        get_observer().on_wdk_request(0.01, _ATTRS)

    with counting_wdk_requests() as tally:
        await asyncio.to_thread(read)
        await asyncio.to_thread(read)
    assert tally.count == 2


async def test_concurrent_blocks_count_only_their_own_requests() -> None:
    async def unit(requests: int) -> int:
        with counting_wdk_requests() as tally:
            for _ in range(requests):
                await asyncio.sleep(0)
                get_observer().on_wdk_request(0.01, _ATTRS)
        return tally.count

    assert list(await asyncio.gather(unit(2), unit(5), unit(3))) == [2, 5, 3]


def test_nested_blocks_count_into_the_innermost() -> None:
    with counting_wdk_requests() as outer:
        get_observer().on_wdk_request(0.01, _ATTRS)
        with counting_wdk_requests() as inner:
            get_observer().on_wdk_request(0.01, _ATTRS)
    assert (outer.count, inner.count) == (1, 1)
