from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk import (
    SearchRequest,
    VEuPathDBClient,
    get_site,
    open_search_gate,
    use_search_gate,
)

from pathfinder.services.search_waits import runs_on_the_deployment_line
from pathfinder.services.strategies import slow_searches

SITE = "plasmodb"
STEP = 7
STRATEGY = 41


@pytest.fixture
def decisions() -> Iterator[list[tuple[str, bool]]]:
    held: list[tuple[str, bool]] = []

    @asynccontextmanager
    async def recording(request: SearchRequest) -> AsyncIterator[None]:
        held.append((request.kind, runs_on_the_deployment_line(request)))
        yield

    use_search_gate(recording)
    token = veupathdb_auth_token_ctx.set("a-registered-token")
    try:
        yield held
    finally:
        veupathdb_auth_token_ctx.reset(token)
        use_search_gate(open_search_gate)
        slow_searches._SLOW_SEARCHES.clear()


def _site(router: respx.MockRouter, base: str) -> None:
    router.get(f"{get_site(SITE).web_base_url}/app").mock(
        return_value=httpx.Response(200)
    )
    router.post(f"{base}/users/current/steps").mock(
        return_value=httpx.Response(200, json={"id": STEP})
    )
    router.post(f"{base}/users/current/strategies").mock(
        return_value=httpx.Response(200, json={"id": STRATEGY})
    )
    router.get(f"{base}/users/current/strategies/{STRATEGY}").mock(
        return_value=httpx.Response(200, json={})
    )
    router.get(f"{base}/users/current/steps/{STEP}").mock(
        return_value=httpx.Response(200, json={})
    )
    router.put(f"{base}/users/current/steps/{STEP}/search-config").mock(
        return_value=httpx.Response(204)
    )
    router.post(url__regex=r".*/reports/standard$").mock(
        return_value=httpx.Response(200, json={"meta": {"totalCount": 3}})
    )


async def _a_save_and_a_count(client: VEuPathDBClient, search: str) -> None:
    await client.post(
        "/users/current/steps",
        json={"searchName": search, "searchConfig": {"parameters": {}}},
    )
    await client.post(
        "/users/current/strategies",
        json={"name": "s", "isSaved": False, "stepTree": {"stepId": STEP}},
    )
    await client.put(
        f"/users/current/steps/{STEP}/search-config", json={"parameters": {}}
    )
    await client.get(f"/users/current/strategies/{STRATEGY}")
    await client.get(f"/users/current/steps/{STEP}")
    await client.post(f"/users/current/steps/{STEP}/reports/standard", json={})
    await client.post(
        f"/record-types/transcript/searches/{search}/reports/standard", json={}
    )


async def test_a_search_marked_slow_waits_only_on_its_own_count(
    decisions: list[tuple[str, bool]],
) -> None:
    slow_searches._SLOW_SEARCHES[(SITE, "GenesByPercentile")] = True
    base = get_site(SITE).service_url
    with respx.mock(assert_all_mocked=True) as router:
        _site(router, base)
        await _a_save_and_a_count(
            VEuPathDBClient(base_url=base, site_id=SITE), "GenesByPercentile"
        )

    assert decisions == [
        ("strategy", False),
        ("step", False),
        ("step", False),
        ("report", True),
    ]


async def test_a_snp_search_waits_on_every_request_that_runs_it(
    decisions: list[tuple[str, bool]],
) -> None:
    base = get_site(SITE).service_url
    with respx.mock(assert_all_mocked=True) as router:
        _site(router, base)
        await _a_save_and_a_count(
            VEuPathDBClient(base_url=base, site_id=SITE), "GenesByNgsSnps"
        )

    assert decisions == [
        ("strategy", True),
        ("step", True),
        ("step", True),
        ("report", True),
    ]
