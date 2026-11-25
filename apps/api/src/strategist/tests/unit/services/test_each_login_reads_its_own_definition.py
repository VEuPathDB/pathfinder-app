"""Requests of two logins through the app each read the search definition once, and
each sees its own."""

from __future__ import annotations

import asyncio
import copy

import httpx
import pytest
from fastapi import FastAPI
from pydantic import TypeAdapter
from veupathdb.json_types import JSONObject
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import VEuPathDBClient

from strategist.main import create_app

pytestmark = pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_molecular_weight.json"),
    reason=NEEDS_QA_RECORDING,
)

SEARCH = "GenesByMolecularWeight"
PROBE = "/probe/search-definition"
_SEEN: TypeAdapter[list[str]] = TypeAdapter(list[str])


def _shown_to(login: str) -> JSONObject:
    body = load_recorded("search_genes_by_molecular_weight").json_body()
    assert isinstance(body, dict)
    shown = copy.deepcopy(body)
    search = shown["searchData"]
    assert isinstance(search, dict)
    search["displayName"] = f"seen by {login}"
    return shown


class Site:
    def __init__(self) -> None:
        self.reads: list[str] = []
        self.client = VEuPathDBClient(
            "https://qa.plasmodb.org/plasmo.qa/service",
            transport=httpx.MockTransport(self._answer),
        )

    def _answer(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/app"):
            return httpx.Response(200, text="")
        cookie = request.headers.get("cookie", "")
        login = next(t for t in ("ada", "bea") if f"Authorization={t}" in cookie)
        self.reads.append(login)
        return httpx.Response(200, json=_shown_to(login))

    async def read(self) -> str:
        details = await self.client.get_search_details("transcript", SEARCH)
        return details.search_data.display_name


@pytest.fixture
def site() -> Site:
    return Site()


@pytest.fixture
def app(site: Site) -> FastAPI:
    built = create_app(include_dev_routes=False)
    both_read = asyncio.Barrier(2)

    async def probe() -> list[str]:
        first = await site.read()
        await both_read.wait()
        return [first, await site.read()]

    built.add_api_route(PROBE, probe, methods=["GET"])
    return built


async def _probe(client: httpx.AsyncClient, login: str) -> list[str]:
    response = await client.get(PROBE, headers={"X-VEUPATHDB-AUTH": login})
    assert response.status_code == 200, response.text
    return _SEEN.validate_python(response.json())


async def test_two_logins_at_once_each_read_and_see_their_own_definition(
    app: FastAPI, site: Site
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        ada, bea = await asyncio.gather(_probe(client, "ada"), _probe(client, "bea"))

    assert ada == ["seen by ada", "seen by ada"]
    assert bea == ["seen by bea", "seen by bea"]
    assert sorted(site.reads) == ["ada", "bea"]
