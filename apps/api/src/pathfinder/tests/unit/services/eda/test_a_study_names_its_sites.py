"""A study card names the genomics sites that publish its dataset, else the portal."""

from __future__ import annotations

import json
from collections.abc import Generator
from unittest.mock import AsyncMock

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import EdaClient, EdaStudiesResponse, EdaStudyOverview
from veupathdb.testing.eda_fixtures import FIXTURE_DIR
from veupathdb_mcp.embeddings import SemanticIndexUnavailableError

from pathfinder.services.eda import catalog
from pathfinder.transport.http.schemas.eda import EdaStudySummaryResponse

pytestmark = pytest.mark.asyncio

# The live dataset reports place these two on tritrypdb and fungidb.
_PUBLISHED = {"DS_2184f85560": ["tritrypdb"], "DS_dd73524c7e": ["fungidb"]}
_BROWSED = [
    "DS_2184f85560",
    "DS_dd73524c7e",
    "EDAUD_Y9I5UEJtdp0JU",
    "EDAUD_J0N5BNAJwN0Np",
    "EDAUD_ZpN54Y0MoV108",
]


async def _fixture_studies(site_id: str) -> list[EdaStudyOverview]:
    del site_id
    raw = json.loads((FIXTURE_DIR / "studies_list.json").read_text())
    return EdaStudiesResponse.model_validate(raw).studies


def _permissions(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json=json.loads((FIXTURE_DIR / "permissions.json").read_text())
    )


@pytest.fixture(autouse=True)
def _fixture_site(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    client = EdaClient(
        base_url="https://plasmodb.org/eda",
        transport=httpx.MockTransport(_permissions),
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _site: client)
    monkeypatch.setattr(catalog, "list_studies", _fixture_studies)
    token = veupathdb_auth_token_ctx.set("sites-test-token")
    yield
    veupathdb_auth_token_ctx.reset(token)


async def test_a_browsed_card_names_its_sites_and_the_portal_for_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publishing = AsyncMock(return_value=_PUBLISHED)
    monkeypatch.setattr(catalog, "sites_publishing", publishing)

    cards = await catalog.browse_studies("plasmodb", limit=100)

    assert sorted((card.dataset_id, card.sites) for card in cards) == sorted(
        [
            ("DS_2184f85560", ["tritrypdb"]),
            ("DS_dd73524c7e", ["fungidb"]),
            ("EDAUD_Y9I5UEJtdp0JU", ["portal"]),
            ("EDAUD_J0N5BNAJwN0Np", ["portal"]),
            ("EDAUD_ZpN54Y0MoV108", ["portal"]),
        ]
    )
    publishing.assert_awaited_once_with(_BROWSED)


async def test_a_card_matched_by_name_names_its_sites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(catalog, "sites_publishing", AsyncMock(return_value=_PUBLISHED))
    monkeypatch.setattr(catalog, "study_index_is_built", AsyncMock(return_value=False))

    found = await catalog.search_studies("plasmodb", "Parastagonospora")

    assert [(card.dataset_id, card.sites) for card in found.cards] == [
        ("DS_dd73524c7e", ["fungidb"])
    ]


async def test_a_store_that_does_not_answer_names_no_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        catalog,
        "sites_publishing",
        AsyncMock(side_effect=SemanticIndexUnavailableError("store down")),
    )

    cards = await catalog.browse_studies("plasmodb", limit=100)

    assert [card.sites for card in cards] == [[], [], [], [], []]


async def test_the_picker_row_carries_the_sites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(catalog, "sites_publishing", AsyncMock(return_value=_PUBLISHED))
    monkeypatch.setattr(catalog, "study_index_is_built", AsyncMock(return_value=False))

    found = await catalog.search_studies("plasmodb", "Parastagonospora")
    row = EdaStudySummaryResponse.model_validate(found.cards[0])

    assert row.model_dump(by_alias=True)["sites"] == ["fungidb"]
