"""A user-dataset search binds one of the researcher's own uploads, checked
against the vocabulary their token reads, never the catalog's cached view."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, call

import pytest
from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKSearch, WDKSearchResponse
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_proposals import (
    CriterionCall,
    refuse_unmatched_values,
)
from pathfinder.services.strategies import user_dataset_searches
from pathfinder.services.strategies.user_dataset_searches import OwnedUpload
from pathfinder.tests._support.qa_recording import qa_recording

_FIXTURES = Path(__file__).parents[3] / "fixtures" / "wdk"


def _search(site: str, name: str) -> WDKSearch:
    raw = json.loads(
        qa_recording(_FIXTURES / f"user_dataset_searches_{site}.json").read_text()
    )
    return WDKSearch.model_validate(next(e for e in raw if e["urlSegment"] == name))


_GENE_LIST = _search("plasmodb", "GenesByUserDatasetGeneList")
# Another account's view: the catalog caches whichever token read it first.
_CACHED_INFOS = format_param_info_typed(
    _search("vectorbase", "GenesByUserDatasetGeneList").parameters or []
)
_UPLOADS = [
    OwnedUpload(
        vdi_id="p0Z51wRgo404A", name="pathfinder-uat-genelist", type_name="genelist"
    ),
    OwnedUpload(
        vdi_id="lhZ5ptRgo014J", name="pathfinder-uat-deseq", type_name="rnaseqrc"
    ),
]
_ONE_UPLOAD = (
    "geneListUserDataset on GenesByUserDatasetGeneList picks one of the "
    "researcher's own uploads: 'pathfinder-uat-genelist' (p0Z51wRgo404A). Pass "
    "the value of the upload the request refers to; nothing was recorded."
)


def _call(value: str | None) -> CriterionCall:
    return CriterionCall(
        criterion_id="c_my_list",
        search_name="GenesByUserDatasetGeneList",
        text="the genes of the gene list I uploaded",
        params={"geneListUserDataset": value},
    )


@pytest.fixture
def account(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    uploads = AsyncMock(return_value=_UPLOADS)
    monkeypatch.setattr(user_dataset_searches, "owned_uploads", uploads)
    monkeypatch.setattr(
        user_dataset_searches,
        "read_search_definition",
        AsyncMock(return_value=_GENE_LIST),
    )
    return uploads


async def _refusal(value: str | None) -> str:
    with pytest.raises(ModelRetry) as refused:
        await refuse_unmatched_values(
            "plasmodb",
            _GENE_LIST,
            _call(value),
            _CACHED_INFOS,
            frozenset(),
            AgentToolState(),
        )
    return str(refused.value)


@pytest.mark.asyncio
async def test_the_researchers_upload_binds_though_the_cached_view_lacks_it(
    account: AsyncMock,
) -> None:
    await refuse_unmatched_values(
        "plasmodb",
        _GENE_LIST,
        _call("p0Z51wRgo404A"),
        _CACHED_INFOS,
        frozenset(),
        AgentToolState(),
    )
    assert account.await_args_list == [call("plasmodb")]


@pytest.mark.asyncio
async def test_a_null_dataset_is_refused_with_the_researchers_uploads(
    account: AsyncMock,
) -> None:
    del account
    assert await _refusal(None) == _ONE_UPLOAD


@pytest.mark.asyncio
async def test_the_sites_placeholder_entry_is_refused(account: AsyncMock) -> None:
    del account
    assert await _refusal("bla") == _ONE_UPLOAD


@pytest.mark.asyncio
async def test_an_account_with_no_upload_of_the_type_is_told_to_upload(
    account: AsyncMock,
) -> None:
    account.return_value = [u for u in _UPLOADS if u.type_name != "genelist"]
    assert await _refusal("p0Z51wRgo404A") == (
        "GenesByUserDatasetGeneList reads the researcher's own genelist uploads, "
        "and this account has none installed on plasmodb, so it cannot run. Bind "
        "nothing for this criterion, and say that the researcher uploads one in "
        "My Data Sets on the site; nothing was recorded."
    )


def _gene_list_listing(term: str, name: str) -> WDKSearch:
    raw = json.loads(
        qa_recording(_FIXTURES / "user_dataset_searches_plasmodb.json").read_text()
    )
    entry = next(e for e in raw if e["urlSegment"] == "GenesByUserDatasetGeneList")
    for parameter in entry["parameters"]:
        if parameter["name"] == "geneListUserDataset":
            parameter["vocabulary"] = [parameter["vocabulary"][0], [term, name, None]]
    return WDKSearch.model_validate(entry)


class _AccountClient:
    """The site's search endpoint, answering with the vocabulary of whoever asks."""

    def __init__(self) -> None:
        self.account = "first"
        self.listings = {
            "first": _GENE_LIST,
            "second": _gene_list_listing("zzZ5secondAcct", "second-account-list"),
        }
        self.uploads = {
            "first": _UPLOADS,
            "second": [
                OwnedUpload(
                    vdi_id="zzZ5secondAcct",
                    name="second-account-list",
                    type_name="genelist",
                )
            ],
        }

    async def get_search_details(
        self, record_type: str, search_name: str, *, expand_params: bool
    ) -> WDKSearchResponse:
        del record_type, search_name, expand_params
        return WDKSearchResponse.model_validate(
            {
                "searchData": self.listings[self.account].model_dump(
                    by_alias=True, mode="json"
                ),
                "validation": {"level": "DISPLAYABLE", "isValid": True},
            }
        )

    async def owned_uploads(self, site_id: str) -> list[OwnedUpload]:
        del site_id
        return self.uploads[self.account]


@pytest.fixture
def two_accounts(monkeypatch: pytest.MonkeyPatch) -> _AccountClient:
    client = _AccountClient()
    monkeypatch.setattr(
        "veupathdb_mcp.catalog.searches.get_wdk_client", lambda site_id: client
    )
    monkeypatch.setattr(user_dataset_searches, "owned_uploads", client.owned_uploads)
    return client


@pytest.mark.asyncio
async def test_each_account_binds_only_its_own_upload_in_sequence(
    two_accounts: _AccountClient,
) -> None:
    await refuse_unmatched_values(
        "plasmodb",
        _GENE_LIST,
        _call("p0Z51wRgo404A"),
        format_param_info_typed(_GENE_LIST.parameters or []),
        frozenset(),
        AgentToolState(),
    )
    two_accounts.account = "second"
    assert await _refusal("p0Z51wRgo404A") == (
        "geneListUserDataset on GenesByUserDatasetGeneList picks one of the "
        "researcher's own uploads: 'second-account-list' (zzZ5secondAcct). Pass "
        "the value of the upload the request refers to; nothing was recorded."
    )
    await refuse_unmatched_values(
        "plasmodb",
        _GENE_LIST,
        _call("zzZ5secondAcct"),
        format_param_info_typed(_GENE_LIST.parameters or []),
        frozenset(),
        AgentToolState(),
    )
    two_accounts.account = "first"
    assert await _refusal("zzZ5secondAcct") == _ONE_UPLOAD
