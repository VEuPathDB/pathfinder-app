"""The per-site preload budget and the retry that clears a degraded site.

One VEuPathDB site that does not answer must cost its own budget and nothing
else: not the other sites' loads, and not the process's readiness.
"""

from __future__ import annotations

import asyncio

import pytest
from veupathdb.errors import WDKError

from pathfinder.platform.errors import SiteUnavailableError
from pathfinder.platform.readiness import ReadinessState
from pathfinder.platform.site_catalogs import (
    preload_catalogs,
    retry_degraded_catalogs,
    run_catalog_retry_loop,
)


class _Loader:
    """A catalog loader whose per-site outcome the test declares."""

    def __init__(self, *, failures: dict[str, BaseException] | None = None) -> None:
        self._failures = dict(failures or {})
        self.calls: list[str] = []

    async def __call__(self, site_id: str) -> None:
        self.calls.append(site_id)
        failure = self._failures.pop(site_id, None)
        if failure is not None:
            raise failure


async def test_every_site_that_loads_is_ready() -> None:
    readiness = ReadinessState()
    loader = _Loader()

    await preload_catalogs(
        loader=loader,
        site_ids=["plasmodb", "toxodb"],
        readiness=readiness,
        budget_seconds=5,
    )

    assert readiness.degraded == []
    assert sorted(loader.calls) == ["plasmodb", "toxodb"]


async def test_a_refusing_site_is_degraded_by_its_error_class() -> None:
    readiness = ReadinessState()
    loader = _Loader(
        failures={"veupathdb": WDKError("https://veupathdb.org refused", status=502)}
    )

    await preload_catalogs(
        loader=loader,
        site_ids=["plasmodb", "veupathdb"],
        readiness=readiness,
        budget_seconds=5,
    )

    assert readiness.degraded == ["veupathdb"]
    assert readiness.catalogs["veupathdb"].error == "WDKError"
    assert readiness.catalogs["plasmodb"].ready is True


async def test_a_site_that_raises_an_app_error_is_degraded_on_its_own() -> None:
    """An application refusal degrades one site, not the whole preload pass."""
    readiness = ReadinessState()
    loader = _Loader(failures={"veupathdb": SiteUnavailableError("veupathdb", None)})

    await preload_catalogs(
        loader=loader,
        site_ids=["plasmodb", "toxodb", "veupathdb"],
        readiness=readiness,
        budget_seconds=5,
    )

    assert readiness.degraded == ["veupathdb"]
    assert readiness.catalogs["veupathdb"].error == "SiteUnavailableError"
    assert readiness.catalogs["plasmodb"].ready is True
    assert readiness.catalogs["toxodb"].ready is True


async def test_a_site_over_its_budget_costs_only_its_budget() -> None:
    readiness = ReadinessState()
    entered = asyncio.Event()

    async def loader(site_id: str) -> None:
        if site_id != "veupathdb":
            return
        entered.set()
        await asyncio.Event().wait()

    loop = asyncio.get_running_loop()
    started = loop.time()
    await preload_catalogs(
        loader=loader,
        site_ids=["plasmodb", "veupathdb"],
        readiness=readiness,
        budget_seconds=0.05,
    )
    elapsed = loop.time() - started

    assert entered.is_set()
    assert readiness.degraded == ["veupathdb"]
    assert readiness.catalogs["veupathdb"].error == "TimeoutError"
    assert readiness.catalogs["plasmodb"].ready is True
    assert elapsed < 1.0


async def test_the_sites_load_concurrently() -> None:
    readiness = ReadinessState()
    site_ids = ["plasmodb", "toxodb", "veupathdb"]
    inside = 0
    all_inside = asyncio.Event()

    async def loader(site_id: str) -> None:
        del site_id
        nonlocal inside
        inside += 1
        if inside == len(site_ids):
            all_inside.set()
        await all_inside.wait()

    await preload_catalogs(
        loader=loader,
        site_ids=site_ids,
        readiness=readiness,
        budget_seconds=5,
    )

    assert all_inside.is_set()
    assert readiness.degraded == []


async def test_the_retry_reloads_only_the_degraded_sites() -> None:
    readiness = ReadinessState()
    loader = _Loader(failures={"veupathdb": WDKError("refused", status=502)})
    await preload_catalogs(
        loader=loader,
        site_ids=["plasmodb", "veupathdb"],
        readiness=readiness,
        budget_seconds=5,
    )
    loader.calls.clear()

    await retry_degraded_catalogs(
        loader=loader,
        readiness=readiness,
        budget_seconds=5,
    )

    assert loader.calls == ["veupathdb"]
    assert readiness.degraded == []
    assert readiness.catalogs["veupathdb"].error is None


async def test_the_retry_loop_waits_the_interval_between_ticks() -> None:
    readiness = ReadinessState()
    loader = _Loader(failures={"veupathdb": WDKError("refused", status=502)})
    await preload_catalogs(
        loader=loader,
        site_ids=["veupathdb"],
        readiness=readiness,
        budget_seconds=5,
    )
    loader.calls.clear()
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)
        if len(waits) == 2:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_catalog_retry_loop(
            loader=loader,
            readiness=readiness,
            budget_seconds=5,
            interval_seconds=60,
            sleep=sleep,
        )

    assert waits == [60, 60]
    assert loader.calls == ["veupathdb"]
    assert readiness.degraded == []
