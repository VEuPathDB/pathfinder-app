"""Dataset to study resolution, and the permission flags that gate an answer."""

from __future__ import annotations

import json
from collections.abc import Callable, Generator

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import EdaClient, EdaStudiesResponse, EdaStudyOverview
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

from pathfinder.services.eda import catalog

FIXTURES = FIXTURE_DIR

pytestmark = pytest.mark.asyncio


def _permissions() -> object:
    return json.loads((FIXTURES / "permissions.json").read_text())


def _permissions_response(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=_permissions())


@pytest.fixture
def eda_client(monkeypatch: pytest.MonkeyPatch) -> EdaClient:
    client = EdaClient(
        base_url="https://plasmodb.org/eda",
        transport=httpx.MockTransport(_permissions_response),
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)
    return client


@pytest.fixture(autouse=True)
def _token() -> Generator[None]:
    token = veupathdb_auth_token_ctx.set("t")
    yield
    veupathdb_auth_token_ctx.reset(token)


async def test_a_known_dataset_resolves_to_its_study_id(eda_client: EdaClient) -> None:
    entry = await catalog.resolve_dataset("plasmodb", "DS_53f554ec6a")
    assert entry.study_id == "STUDY_53f554ec6a"
    await eda_client.close()


async def test_resolution_never_derives_the_study_id_from_the_dataset_id(
    eda_client: EdaClient,
) -> None:
    """STUDY_<suffix> equals DS_<suffix> for only 684 of 747 curated studies."""
    entry = await catalog.resolve_dataset("plasmodb", "DS_dd73524c7e")
    assert entry.study_id == "STUDY_bf43a6913c"
    await eda_client.close()


async def test_an_unknown_dataset_raises_with_the_id_named(
    eda_client: EdaClient,
) -> None:
    with pytest.raises(catalog.UnknownEdaDatasetError) as excinfo:
        await catalog.resolve_dataset("plasmodb", "EDAUD_slI5M0RwIg0Zw")
    assert "EDAUD_slI5M0RwIg0Zw" in str(excinfo.value)
    await eda_client.close()


async def test_resolution_is_cached_per_site_so_one_call_serves_a_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=_permissions())

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)

    await catalog.resolve_dataset("plasmodb", "DS_53f554ec6a")
    await catalog.resolve_dataset("plasmodb", "DS_16bc228c8e")
    await client.close()
    assert calls == ["/eda/permissions"]


def _routed(calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/permissions"):
            return httpx.Response(200, json=_permissions())
        if request.url.path.endswith("/studies"):
            return httpx.Response(
                200, json=json.loads((FIXTURES / "studies_list.json").read_text())
            )
        return httpx.Response(
            200,
            json=json.loads((FIXTURES / "study_detail_phenotype.json").read_text()),
        )

    return httpx.MockTransport(handler)


async def test_a_listed_dataset_reaches_a_cached_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The detail call takes the STUDY id, and only permissions supplies it."""
    calls: list[str] = []
    client = EdaClient(base_url="https://plasmodb.org/eda", transport=_routed(calls))
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)

    entry, detail = await catalog.get_study_detail_for_dataset(
        "plasmodb", "DS_dd73524c7e"
    )
    again = await catalog.get_study_detail_for_dataset("plasmodb", "DS_dd73524c7e")
    await client.close()
    assert entry.study_id == "STUDY_bf43a6913c"
    assert detail.root_entity.id == "GENE_PHENOTYPE_DATA_ENTITY"
    assert again[1] is detail
    assert calls == [
        "/eda/permissions",
        "/eda/studies",
        "/eda/studies/STUDY_bf43a6913c",
    ]


async def test_a_dataset_whose_study_is_unlisted_reads_its_detail_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A study with no /studies row reports no version, so nothing caches it."""
    calls: list[str] = []
    client = EdaClient(base_url="https://plasmodb.org/eda", transport=_routed(calls))
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)

    entry, detail = await catalog.get_study_detail_for_dataset(
        "plasmodb", "DS_53f554ec6a"
    )
    await catalog.get_study_detail_for_dataset("plasmodb", "DS_53f554ec6a")
    await client.close()
    assert entry.study_id == "STUDY_53f554ec6a"
    assert detail.id == "STUDY_53f554ec6a"
    assert calls.count("/eda/studies/STUDY_53f554ec6a") == 2


_RESTRICTED = "restricted-token"
_SERVICE = "service-token"


def _per_account(seen: list[str]) -> httpx.MockTransport:
    """The service account reads the whole fixture; the second account reads none."""

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.headers["Cookie"].removeprefix("Authorization=")
        seen.append(token)
        if token == _SERVICE:
            return httpx.Response(200, json=_permissions())
        return httpx.Response(200, json={"perDataset": {}})

    return httpx.MockTransport(handler)


async def test_a_second_account_is_not_served_the_first_account_s_datasets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The permissions answer is the caller's, so a second token reads its own."""
    seen: list[str] = []
    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=_per_account(seen)
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)

    veupathdb_auth_token_ctx.set(_SERVICE)
    entry = await catalog.resolve_dataset("plasmodb", "DS_53f554ec6a")
    veupathdb_auth_token_ctx.set(_RESTRICTED)
    with pytest.raises(catalog.UnknownEdaDatasetError):
        await catalog.resolve_dataset("plasmodb", "DS_53f554ec6a")
    await client.close()

    assert entry.study_id == "STUDY_53f554ec6a"
    assert seen == [_SERVICE, _RESTRICTED]


async def test_two_accounts_in_one_process_hold_two_permission_maps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second account's browse is empty while the first account's is not."""
    seen: list[str] = []
    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=_per_account(seen)
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)
    monkeypatch.setattr(catalog, "list_studies", _fixture_studies)

    veupathdb_auth_token_ctx.set(_SERVICE)
    service_cards = await catalog.browse_studies("plasmodb", limit=100)
    veupathdb_auth_token_ctx.set(_RESTRICTED)
    restricted_cards = await catalog.browse_studies("plasmodb", limit=100)
    await client.close()

    assert len(service_cards) > 0
    assert restricted_cards == []


async def test_one_account_asking_twice_still_reads_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=_per_account(seen)
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)

    veupathdb_auth_token_ctx.set(_SERVICE)
    await catalog.resolve_dataset("plasmodb", "DS_53f554ec6a")
    await catalog.resolve_dataset("plasmodb", "DS_16bc228c8e")
    await client.close()

    assert seen == [_SERVICE]


async def _fixture_studies(site_id: str) -> list[EdaStudyOverview]:
    del site_id
    raw = json.loads((FIXTURES / "studies_list.json").read_text())
    return EdaStudiesResponse.model_validate(raw).studies


async def test_clearing_the_cache_forces_a_refetch(
    monkeypatch: pytest.MonkeyPatch,
    drop_eda_study_caches: Callable[[], None],
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=_permissions())

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)

    await catalog.resolve_dataset("plasmodb", "DS_53f554ec6a")
    drop_eda_study_caches()
    await catalog.resolve_dataset("plasmodb", "DS_53f554ec6a")
    await client.close()
    assert len(calls) == 2
