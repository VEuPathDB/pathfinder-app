"""A study that another site publishes is refused at bind on a component site."""

from __future__ import annotations

import json
from collections.abc import Generator
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import (
    EdaClient,
    EdaPermissionEntry,
    EdaStudiesResponse,
    EdaStudyDetail,
    EdaStudyOverview,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR
from veupathdb_mcp.embeddings import SemanticIndexUnavailableError

from pathfinder.services.eda import binding, catalog, study_site
from pathfinder.services.eda.study_site import (
    StudyOnAnotherSiteError,
    StudySitesUnreadableError,
    not_here,
)
from pathfinder.tests._support.eda_doubles import permission_entry, study_of

pytestmark = pytest.mark.asyncio

_MOSQUITO = "DS_89c1f6f48a"


def test_a_study_vectorbase_publishes_is_not_opened_on_plasmodb() -> None:
    assert not_here("plasmodb", ["vectorbase"], own=False) == (
        "This study is on VectorBase; its genes are not PlasmoDB genes. "
        "Ask on VectorBase."
    )


def test_a_study_no_genomics_site_publishes_names_the_portal() -> None:
    assert not_here("plasmodb", ["portal"], own=False) == (
        "This study is on the VEuPathDB Portal; its genes are not PlasmoDB "
        "genes. Ask on the VEuPathDB Portal."
    )


def test_a_study_two_sites_publish_names_both() -> None:
    assert not_here("plasmodb", ["tritrypdb", "fungidb"], own=False) == (
        "This study is on TriTrypDB and FungiDB; its genes are not PlasmoDB "
        "genes. Ask on TriTrypDB or FungiDB."
    )


def test_a_study_opens_where_published_on_the_portal_and_when_own() -> None:
    opened = {
        "the site publishes it": not_here(
            "plasmodb", ["plasmodb", "vectorbase"], own=False
        ),
        "the portal": not_here("veupathdb", ["vectorbase"], own=False),
        "the researcher's own": not_here("plasmodb", ["portal"], own=True),
    }

    assert opened == dict.fromkeys(opened, None)


def _curated(entry: EdaPermissionEntry) -> AsyncMock:
    detail: EdaStudyDetail = study_of([], entity_id="ENT_g")
    return AsyncMock(return_value=(entry, detail))


async def test_bind_refuses_a_study_another_site_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened = AsyncMock(return_value="an_1")
    monkeypatch.setattr(
        binding, "get_study_detail_for_dataset", _curated(permission_entry())
    )
    monkeypatch.setattr(
        study_site,
        "sites_publishing",
        AsyncMock(return_value={_MOSQUITO: ["vectorbase"]}),
    )
    monkeypatch.setattr(binding, "open_analysis", opened)

    with pytest.raises(StudyOnAnotherSiteError) as refused:
        await binding.bind_analysis(
            "plasmodb",
            dataset_id=_MOSQUITO,
            conversation_id=uuid4(),
            display_name="blood meal",
        )

    assert refused.value.detail == (
        "This study is on VectorBase; its genes are not PlasmoDB genes. "
        "Ask on VectorBase."
    )
    assert refused.value.status == 422
    opened.assert_not_awaited()


async def test_bind_refuses_a_study_no_genomics_site_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        binding, "get_study_detail_for_dataset", _curated(permission_entry())
    )
    monkeypatch.setattr(study_site, "sites_publishing", AsyncMock(return_value={}))
    monkeypatch.setattr(binding, "open_analysis", AsyncMock(return_value="an_1"))

    with pytest.raises(StudyOnAnotherSiteError) as refused:
        await binding.bind_analysis(
            "plasmodb",
            dataset_id=_MOSQUITO,
            conversation_id=uuid4(),
            display_name="blood meal",
        )

    assert refused.value.detail == (
        "This study is on the VEuPathDB Portal; its genes are not PlasmoDB "
        "genes. Ask on the VEuPathDB Portal."
    )


async def test_bind_refuses_when_the_publishing_sites_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened = AsyncMock(return_value="an_1")
    monkeypatch.setattr(
        binding, "get_study_detail_for_dataset", _curated(permission_entry())
    )
    monkeypatch.setattr(
        study_site,
        "sites_publishing",
        AsyncMock(side_effect=SemanticIndexUnavailableError("store down")),
    )
    monkeypatch.setattr(binding, "open_analysis", opened)

    with pytest.raises(StudySitesUnreadableError) as refused:
        await binding.bind_analysis(
            "plasmodb",
            dataset_id=_MOSQUITO,
            conversation_id=uuid4(),
            display_name="blood meal",
        )

    assert refused.value.status == 503
    opened.assert_not_awaited()


async def test_the_publishing_sites_are_not_read_for_the_researchers_own_study(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    own = permission_entry().model_copy(update={"is_user_study": True})
    publishing = AsyncMock(return_value={})
    monkeypatch.setattr(study_site, "sites_publishing", publishing)

    await study_site.refuse_a_study_another_site_publishes(
        "plasmodb", "EDAUD_Y9I5UEJtdp0JU", entry=own
    )

    assert publishing.await_args_list == []


async def test_the_publishing_sites_are_not_read_on_the_portal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publishing = AsyncMock(return_value={})
    monkeypatch.setattr(study_site, "sites_publishing", publishing)

    await study_site.refuse_a_study_another_site_publishes(
        "veupathdb", _MOSQUITO, entry=permission_entry()
    )

    assert publishing.await_args_list == []


async def _fixture_studies(site_id: str) -> list[EdaStudyOverview]:
    del site_id
    raw = json.loads((FIXTURE_DIR / "studies_list.json").read_text())
    return EdaStudiesResponse.model_validate(raw).studies


def _permissions(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json=json.loads((FIXTURE_DIR / "permissions.json").read_text())
    )


@pytest.fixture
def fixture_site(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    client = EdaClient(
        base_url="https://plasmodb.org/eda",
        transport=httpx.MockTransport(_permissions),
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)
    monkeypatch.setattr(catalog, "list_studies", _fixture_studies)
    token = veupathdb_auth_token_ctx.set("sites-test-token")
    yield
    veupathdb_auth_token_ctx.reset(token)


async def test_a_listed_card_another_site_publishes_says_it_is_not_opened_here(
    monkeypatch: pytest.MonkeyPatch, fixture_site: None
) -> None:
    del fixture_site
    monkeypatch.setattr(
        catalog,
        "sites_publishing",
        AsyncMock(
            return_value={"DS_2184f85560": ["tritrypdb"], "DS_dd73524c7e": ["plasmodb"]}
        ),
    )

    cards = await catalog.browse_studies("plasmodb", limit=100)

    assert {card.dataset_id: card.not_here for card in cards} == {
        "DS_2184f85560": (
            "This study is on TriTrypDB; its genes are not PlasmoDB genes. "
            "Ask on TriTrypDB."
        ),
        "DS_dd73524c7e": None,
        "EDAUD_Y9I5UEJtdp0JU": None,
        "EDAUD_J0N5BNAJwN0Np": None,
        "EDAUD_ZpN54Y0MoV108": None,
    }


async def test_a_listed_card_on_the_portal_opens(
    monkeypatch: pytest.MonkeyPatch, fixture_site: None
) -> None:
    del fixture_site
    monkeypatch.setattr(
        catalog,
        "sites_publishing",
        AsyncMock(return_value={"DS_2184f85560": ["tritrypdb"]}),
    )

    cards = await catalog.browse_studies("veupathdb", limit=100)

    assert [card.not_here for card in cards] == [None] * len(cards)
