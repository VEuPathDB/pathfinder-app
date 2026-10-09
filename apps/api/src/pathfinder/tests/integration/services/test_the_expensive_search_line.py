from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from veupathdb.wdk import SearchGate, SearchRequest
from veupathdb_mcp.search_line import ExpensiveSearchLine, search_line_gate

from pathfinder.services.search_waits import runs_on_the_deployment_line
from pathfinder.services.strategies import slow_searches
from pathfinder.tests._support.search_load import a_counted_site

_SNP_REPORT = "/record-types/transcript/searches/GenesByNgsSnps/reports/standard"
_PERCENTILE_REPORT = (
    "/record-types/transcript/searches/GenesByPercentile/reports/standard"
)


@pytest.fixture
async def two_processes(db_engine: AsyncEngine) -> AsyncIterator[list[SearchGate]]:
    url = db_engine.url.render_as_string(hide_password=False)
    engines = [
        create_async_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
        for _ in range(2)
    ]
    try:
        yield [
            search_line_gate(ExpensiveSearchLine(engine), runs_on_the_deployment_line)
            for engine in engines
        ]
    finally:
        for engine in engines:
            await engine.dispose()


@pytest.fixture
def a_slow_percentile_search() -> Iterator[None]:
    slow_searches._SLOW_SEARCHES[("plasmodb", "GenesByPercentile")] = True
    yield
    slow_searches._SLOW_SEARCHES.clear()


async def _both(gates: list[SearchGate], search_name: str, path: str) -> int:
    request = SearchRequest(
        site_id="plasmodb", kind="report", search_names=frozenset({search_name})
    )
    with a_counted_site() as (client, load):

        async def search(gate: SearchGate) -> object:
            async with gate(request):
                return await client.post(path, json={})

        await asyncio.gather(*(search(gate) for gate in gates))
    return load.most_in_flight


async def test_two_snp_searches_of_two_processes_reach_the_site_in_turn(
    two_processes: list[SearchGate],
) -> None:
    assert await _both(two_processes, "GenesByNgsSnps", _SNP_REPORT) == 1


@pytest.mark.usefixtures("a_slow_percentile_search")
async def test_a_search_marked_slow_takes_the_same_line(
    two_processes: list[SearchGate],
) -> None:
    assert await _both(two_processes, "GenesByPercentile", _PERCENTILE_REPORT) == 1


async def test_a_cheap_search_of_two_processes_runs_side_by_side(
    two_processes: list[SearchGate],
) -> None:
    text_report = "/record-types/transcript/searches/GenesByText/reports/standard"

    assert await _both(two_processes, "GenesByText", text_report) == 2
