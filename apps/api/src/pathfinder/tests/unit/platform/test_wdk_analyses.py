"""The client endpoints for step analyses, step filters and analysis results.

The analyses list is a summary, not a full instance. Writing one part of a
search config keeps the rest of it, and a 204 result body is not a result.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk.analysis_result import (
    WDKAnalysisNotReadyError,
)
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.wdk_models import WDKFilterValue
from veupathdb_mcp.wdk.enrichment.types import EnrichmentResult

from pathfinder.platform.errors import AppError, ErrorCode

pytestmark = pytest.mark.usefixtures("wdk_request_token")

REGISTERED_TEST_TOKEN = "registered.transport.token"


@pytest.fixture
def wdk_request_token() -> Generator[str]:
    """Act as a registered VEuPathDB user.

    A test that addresses a resource inside a user's WDK account needs one:
    without it the transport refuses the call.
    """
    reset = veupathdb_auth_token_ctx.set(REGISTERED_TEST_TOKEN)
    yield REGISTERED_TEST_TOKEN
    veupathdb_auth_token_ctx.reset(reset)


_LIVE_ENTRY: dict[str, Any] = {
    "displayName": "Word Enrichment",
    "analysisId": 203635253,
}

_COLUMN_FILTERS: dict[str, Any] = {
    "gene_product": {"values": ["kinase"], "includeUnknown": False}
}

_STEP: dict[str, Any] = {
    "id": 9,
    "searchName": "GenesByMolecularWeight",
    "recordClassName": "transcript",
    "searchConfig": {
        "parameters": {"min_molecular_weight": "10000"},
        "filters": [{"name": "existing_filter", "disabled": False, "value": None}],
        "columnFilters": _COLUMN_FILTERS,
        "wdkWeight": 7,
    },
}

_TRANSFORM_STEP: dict[str, Any] = {
    "id": 9,
    "searchName": "GenesByOrthologs",
    "recordClassName": "transcript",
    "validation": {"level": "SEMANTIC", "isValid": True},
    "searchConfig": {
        "parameters": {"gene_result": "440085983", "organism": "[]"},
        "wdkWeight": 0,
    },
}


class _Fixed(httpx.AsyncBaseTransport):
    """Answers every request with one canned response."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        del request
        return self._response


class _Recorder:
    """Captures the PUT body instead of reaching WDK."""

    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []

    async def __call__(
        self, path: str, json: dict[str, Any] | None = None, **_: object
    ) -> Any:
        del path
        self.bodies.append(json or {})
        return None

    @property
    def body(self) -> dict[str, Any]:
        return self.bodies[-1]


async def _client_answering(response: httpx.Response) -> VEuPathDBClient:
    client = VEuPathDBClient("https://example.invalid/service")
    async with client._client_lock:
        client._client = httpx.AsyncClient(
            base_url=client.base_url, transport=_Fixed(response)
        )
    return client


async def _client_listing(body: Any) -> VEuPathDBClient:
    return await _client_answering(
        httpx.Response(200, json=body, headers={"content-type": "application/json"})
    )


def _writing_client(
    monkeypatch: pytest.MonkeyPatch, step: dict[str, Any] = _STEP
) -> tuple[VEuPathDBClient, _Recorder]:
    async def read(path: str, **_: object) -> Any:
        del path
        return step

    client = VEuPathDBClient("https://example.invalid/service")
    put = _Recorder()
    monkeypatch.setattr(client, "get", read)
    monkeypatch.setattr(client, "put", put)
    return client, put


async def _set_one(client: VEuPathDBClient) -> None:
    await client.update_step_filters(
        "1", 9, [WDKFilterValue(name="new_filter", value=None, disabled=False)]
    )


class TestTheLiveShapeParses:
    async def test_an_entry_is_returned(self) -> None:
        client = await _client_listing([_LIVE_ENTRY])

        assert len(await client.list_step_analyses("1", 9)) == 1

    async def test_the_analysis_id_survives(self) -> None:
        client = await _client_listing([_LIVE_ENTRY])

        assert (await client.list_step_analyses("1", 9))[0].analysis_id == 203635253

    async def test_the_display_name_survives(self) -> None:
        client = await _client_listing([_LIVE_ENTRY])

        entry = (await client.list_step_analyses("1", 9))[0]
        assert entry.display_name == "Word Enrichment"

    async def test_several_entries_all_parse(self) -> None:
        client = await _client_listing(
            [_LIVE_ENTRY, {"displayName": "GO", "analysisId": 7}]
        )

        assert len(await client.list_step_analyses("1", 9)) == 2


class TestABadEntryIsStillSkipped:
    async def test_an_entry_without_an_id_is_dropped(self) -> None:
        client = await _client_listing([{"displayName": "no id"}, _LIVE_ENTRY])

        assert len(await client.list_step_analyses("1", 9)) == 1

    async def test_an_empty_list_is_still_empty(self) -> None:
        client = await _client_listing([])

        assert await client.list_step_analyses("1", 9) == []


class TestTheResultEndpoint:
    async def test_no_content_is_not_a_result(self) -> None:
        client = await _client_answering(httpx.Response(204))

        with pytest.raises(WDKAnalysisNotReadyError):
            await client.get_analysis_result("1", 9, 4)

    async def test_a_real_result_still_comes_back(self) -> None:
        body = {"resultData": [{"goId": "GO:0004672", "pValue": "1e-9"}]}
        client = await _client_listing(body)

        assert await client.get_analysis_result("1", 9, 4) == body

    async def test_an_empty_result_object_is_still_a_result(self) -> None:
        # A plugin that ran and found nothing sends a body.
        client = await _client_listing({})

        assert await client.get_analysis_result("1", 9, 4) == {}


class TestTheTwoEmptyResultsAreToldApart:
    def test_the_batch_path_records_it_as_a_failure(self) -> None:
        # The enrichment batch turns an AppError into a result carrying `error`.
        not_ready = WDKAnalysisNotReadyError(9, 4)

        assert isinstance(not_ready, (AppError, VEuPathDBError))
        assert (not_ready.status, not_ready.code) == (502, ErrorCode.WDK_ERROR)

    def test_an_enrichment_that_found_nothing_carries_no_error(self) -> None:
        found_nothing = EnrichmentResult(
            analysis_type="go_process", terms=[], total_genes_analyzed=0
        )

        assert (found_nothing.terms, found_nothing.error) == ([], None)

    def test_a_result_that_could_not_be_fetched_carries_the_error(self) -> None:
        could_not_fetch = EnrichmentResult(
            analysis_type="go_process",
            terms=[],
            total_genes_analyzed=0,
            error=str(WDKAnalysisNotReadyError(9, 4)),
        )

        assert could_not_fetch.error is not None
        assert could_not_fetch != EnrichmentResult(
            analysis_type="go_process", terms=[], total_genes_analyzed=0
        )


class TestTheRestOfTheConfigSurvives:
    """A column filter narrows the answer and WDK counts it in ``estimatedSize``.

    Rewriting the config from a subset of its keys drops that filter, widens
    the result, and answers 204.
    """

    async def test_column_filters_are_kept(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, put = _writing_client(monkeypatch)

        await _set_one(client)

        assert put.body["columnFilters"] == _COLUMN_FILTERS

    async def test_parameters_are_kept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, put = _writing_client(monkeypatch)

        await _set_one(client)

        assert put.body["parameters"] == {"min_molecular_weight": "10000"}

    async def test_the_weight_is_kept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, put = _writing_client(monkeypatch)

        await _set_one(client)

        assert put.body["wdkWeight"] == 7


class TestTheFiltersAreReplaced:
    async def test_the_new_filter_is_written(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, put = _writing_client(monkeypatch)

        await _set_one(client)

        assert [f["name"] for f in put.body["filters"]] == ["new_filter"]

    async def test_view_filters_are_not_sent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # viewFilters does not belong to searchConfig; WDK's schema rejects it.
        client, put = _writing_client(monkeypatch)

        await _set_one(client)

        assert "viewFilters" not in put.body


async def test_wdk_step_003_an_answer_parameter_survives_a_filter_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Dropping an answer parameter is changing it, which is a 422.
    client, put = _writing_client(monkeypatch, _TRANSFORM_STEP)

    await _set_one(client)

    assert put.body["parameters"]["gene_result"] == "440085983"
