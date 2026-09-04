"""The catalogs a process holds are bounded by a memory budget.

Per-site catalogs and semantic indexes load on demand. Without a bound the
process grows with every site a session touches until the kernel kills it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from pathfinder.integrations.veupathdb import discovery_service
from pathfinder.integrations.veupathdb.discovery_service import DiscoveryService

MIB = 1024 * 1024


@dataclass
class _Catalogs:
    """What the fake catalogs report, and what they recorded."""

    sizes: dict[str, int] = field(default_factory=dict)
    loads: list[str] = field(default_factory=list)
    gate: asyncio.Event | None = None
    entered: asyncio.Event | None = None


_state = _Catalogs()


class _FakeCatalog:
    """A catalog that records its loads and reports a fixed accounted size."""

    def __init__(self, site_id: str) -> None:
        self.site_id = site_id

    async def load(self, client: object) -> None:
        del client
        _state.loads.append(self.site_id)
        if _state.entered is not None:
            _state.entered.set()
        if _state.gate is not None:
            await _state.gate.wait()

    @property
    def memory_bytes(self) -> int:
        return _state.sizes.get(self.site_id, 10 * MIB)


class _FakeRouter:
    def get_client(self, site_id: str) -> str:
        return f"client-{site_id}"


@pytest.fixture(autouse=True)
def catalogs(monkeypatch: pytest.MonkeyPatch) -> _Catalogs:
    _state.sizes.clear()
    _state.loads.clear()
    _state.gate = None
    _state.entered = None
    monkeypatch.setattr(discovery_service, "SearchCatalog", _FakeCatalog)
    monkeypatch.setattr(discovery_service, "get_site_router", _FakeRouter)
    return _state


async def test_a_second_touch_of_a_held_site_does_not_reload_it(
    catalogs: _Catalogs,
) -> None:
    service = DiscoveryService(memory_budget_bytes=100 * MIB)

    await service.get_catalog("plasmodb")
    await service.get_catalog("plasmodb")

    assert catalogs.loads == ["plasmodb"]


async def test_the_least_recently_used_site_leaves_when_the_budget_is_reached(
    catalogs: _Catalogs,
) -> None:
    catalogs.sizes.update({"a": 40 * MIB, "b": 40 * MIB, "c": 40 * MIB})
    service = DiscoveryService(memory_budget_bytes=100 * MIB)

    await service.get_catalog("a")
    await service.get_catalog("b")
    await service.get_catalog("a")
    await service.get_catalog("c")

    assert service.held_sites() == ["a", "c"]


async def test_the_held_bytes_never_pass_the_budget(catalogs: _Catalogs) -> None:
    catalogs.sizes.update(dict.fromkeys(("a", "b", "c", "d", "e"), 30 * MIB))
    service = DiscoveryService(memory_budget_bytes=100 * MIB)

    for name in ("a", "b", "c", "d", "e"):
        await service.get_catalog(name)

    assert service.held_bytes() <= 100 * MIB
    assert len(service.held_sites()) == 3


async def test_an_evicted_site_is_rebuilt_on_the_next_touch(
    catalogs: _Catalogs,
) -> None:
    catalogs.sizes.update({"a": 60 * MIB, "b": 60 * MIB})
    service = DiscoveryService(memory_budget_bytes=100 * MIB)

    await service.get_catalog("a")
    await service.get_catalog("b")
    assert service.held_sites() == ["b"]

    await service.get_catalog("a")

    assert catalogs.loads == ["a", "b", "a"]


async def test_a_site_larger_than_the_budget_is_served_and_not_held(
    catalogs: _Catalogs,
) -> None:
    catalogs.sizes["huge"] = 200 * MIB
    service = DiscoveryService(memory_budget_bytes=100 * MIB)

    catalog = await service.get_catalog("huge")

    assert catalog.site_id == "huge"
    assert service.held_sites() == []


async def test_two_callers_of_one_site_build_it_once(catalogs: _Catalogs) -> None:
    catalogs.gate = asyncio.Event()
    catalogs.entered = asyncio.Event()
    service = DiscoveryService(memory_budget_bytes=100 * MIB)

    first = asyncio.create_task(service.get_catalog("plasmodb"))
    await catalogs.entered.wait()
    second = asyncio.create_task(service.get_catalog("plasmodb"))
    await asyncio.sleep(0)
    catalogs.gate.set()
    await asyncio.gather(first, second)

    assert catalogs.loads == ["plasmodb"]
