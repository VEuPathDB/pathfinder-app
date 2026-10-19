"""A request, an agent turn and a background job each read a search definition once,
under their own login, and keep nothing after they end."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import TypeAdapter
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import VEuPathDBClient, WDKSearchResponse

from pathfinder.jobs.job_context import WdkJobContext, WdkJobState
from pathfinder.main import create_app
from pathfinder.services.search_waits import researcher_search_turn

pytestmark = pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_molecular_weight.json"),
    reason=NEEDS_QA_RECORDING,
)

SEARCH = "GenesByMolecularWeight"
PROBE = "/probe/search-definition"
_SEEN: TypeAdapter[list[str]] = TypeAdapter(list[str])


class Site:
    """A site client whose definition read answers the asking login by name."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.reads: list[str | None] = []
        self.client = VEuPathDBClient("https://qa.plasmodb.org/plasmo.qa/service")
        monkeypatch.setattr(self.client, "get", self._get)

    async def _get(self, path: str, **_: object) -> dict[str, Any]:
        del path
        login = veupathdb_auth_token_ctx.get()
        self.reads.append(login)
        recorded = WDKSearchResponse.model_validate(
            load_recorded("search_genes_by_molecular_weight").json_body()
        )
        named = recorded.search_data.model_copy(
            update={"display_name": f"seen by {login}"}
        )
        return recorded.model_copy(update={"search_data": named}).model_dump(
            by_alias=True, mode="json"
        )

    async def read(self) -> str:
        details = await self.client.get_search_details("transcript", SEARCH)
        return details.search_data.display_name


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> Site:
    return Site(monkeypatch)


@pytest.fixture
def app(site: Site) -> FastAPI:
    built = create_app(include_dev_routes=False)
    both_read = asyncio.Barrier(2)

    async def probe(together: bool = False) -> list[str]:
        first = await site.read()
        if together:
            await both_read.wait()
        return [first, await site.read()]

    built.add_api_route(PROBE, probe, methods=["GET"])
    return built


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def _probe(
    client: httpx.AsyncClient, login: str, *, together: bool = False
) -> list[str]:
    response = await client.get(
        PROBE,
        params={"together": str(together).lower()},
        headers={"X-VEUPATHDB-AUTH": login},
    )
    assert response.status_code == 200, response.text
    return _SEEN.validate_python(response.json())


async def test_one_request_reads_a_definition_once(app: FastAPI, site: Site) -> None:
    async with _client(app) as client:
        seen = await _probe(client, "ada")

    assert seen == ["seen by ada", "seen by ada"]
    assert site.reads == ["ada"]


async def test_the_next_request_reads_it_again(app: FastAPI, site: Site) -> None:
    async with _client(app) as client:
        await _probe(client, "ada")
        await _probe(client, "ada")

    assert site.reads == ["ada", "ada"]


async def test_two_logins_saving_at_once_each_see_their_own_definition(
    app: FastAPI, site: Site
) -> None:
    async with _client(app) as client:
        ada, bea = await asyncio.gather(
            _probe(client, "ada", together=True),
            _probe(client, "bea", together=True),
        )

    assert ada == ["seen by ada", "seen by ada"]
    assert bea == ["seen by bea", "seen by bea"]
    assert sorted(site.reads, key=str) == ["ada", "bea"]


class _Unheard:
    conversation_id = uuid4()
    turn_id = uuid4()

    async def write(self, chunk: dict[str, Any]) -> int:
        del chunk
        raise AssertionError


@pytest.fixture
def as_ada() -> Iterator[None]:
    reset = veupathdb_auth_token_ctx.set("ada")
    yield
    veupathdb_auth_token_ctx.reset(reset)


async def test_an_agent_turn_reads_a_definition_once(site: Site, as_ada: None) -> None:
    with researcher_search_turn(_Unheard()):
        await site.read()
        await site.read()
    await site.read()

    assert site.reads == ["ada", "ada"]


async def test_a_background_job_reads_a_definition_once(site: Site) -> None:
    state = WdkJobState.model_validate({"veupathdb_auth_token": "ada"})

    async with WdkJobContext().restore(state):
        await site.read()
        await site.read()
    async with WdkJobContext().restore(state):
        await site.read()

    assert site.reads == ["ada", "ada"]
