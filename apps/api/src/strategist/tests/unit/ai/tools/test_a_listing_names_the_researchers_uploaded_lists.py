from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKSearch
from veupathdb.wdk.vdi.client import VdiServiceError

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone import _frame_gene_set, gene_sets
from strategist.ai.tools.standalone._frame_proposals import (
    CriterionCall,
    refuse_unmatched_values,
)
from strategist.ai.tools.standalone.gene_set_models import (
    LISTING_PAGE,
    GeneSetListResponse,
    UploadedGeneList,
)
from strategist.domain.strategy.operational_spec import Criterion
from strategist.services.gene_sets.types import GeneSet
from strategist.services.strategies import user_dataset_searches
from strategist.services.strategies.user_dataset_searches import (
    OwnedUpload,
    UserDatasetOffer,
    uploaded_gene_lists,
)
from strategist.tests._support.qa_recording import qa_recording
from strategist.tests._support.tool_returns import returned
from strategist.tests.unit.ai.tools.conftest import agent_run_context

_FIXTURES = Path(__file__).parents[3] / "fixtures" / "wdk"


def _recorded() -> list[WDKSearch]:
    raw = json.loads(
        qa_recording(_FIXTURES / "user_dataset_searches_plasmodb.json").read_text()
    )
    return [WDKSearch.model_validate(entry) for entry in raw]


_SEARCHES = _recorded()
_GENE_LIST = next(s for s in _SEARCHES if s.url_segment == "GenesByUserDatasetGeneList")
_UPLOADS = [
    OwnedUpload(
        vdi_id="Ud18NklEhB0wF", name="pathfinder-uat-genelist", type_name="genelist"
    ),
    OwnedUpload(
        vdi_id="Y518ZRlgBR0Q5", name="pathfinder-uat-deseq", type_name="rnaseqrc"
    ),
]
_THE_LIST = UploadedGeneList(
    name="pathfinder-uat-genelist",
    value="Ud18NklEhB0wF",
    search_name="GenesByUserDatasetGeneList",
    parameter="geneListUserDataset",
)


def _serve_the_site(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        user_dataset_searches, "get_raw_searches", AsyncMock(return_value=_SEARCHES)
    )

    async def _definition(_site: str, _record_type: str, name: str) -> WDKSearch:
        return next(s for s in _SEARCHES if s.url_segment == name)

    monkeypatch.setattr(user_dataset_searches, "read_search_definition", _definition)
    monkeypatch.setattr(
        user_dataset_searches, "owned_uploads", AsyncMock(return_value=_UPLOADS)
    )


def _saved(count: int) -> list[GeneSet]:
    return [
        GeneSet(
            id=f"gs-{n}",
            name=f"set {n}",
            site_id="plasmodb",
            gene_ids=["PF3D7_0304600", "PF3D7_1133400"],
            source="paste",
        )
        for n in range(count)
    ]


def _store(monkeypatch: pytest.MonkeyPatch, stored: list[GeneSet]) -> None:
    async def _listed(*, site_id: str, user_id: UUID | None) -> list[GeneSet]:
        del site_id, user_id
        return stored

    monkeypatch.setattr(gene_sets, "list_stored_gene_sets", _listed)


def _offer(name: str, value: str) -> UserDatasetOffer:
    return UserDatasetOffer(
        search_name="GenesByUserDatasetGeneList",
        search_display_name="Gene List (User Datasets)",
        parameter="geneListUserDataset",
        value=value,
        upload_name=name,
    )


def _uploaded(count: int) -> list[UserDatasetOffer]:
    return [_offer(f"upload {n}", f"id{n}") for n in range(count)]


def _lists_on_the_site(
    monkeypatch: pytest.MonkeyPatch, lists: list[UserDatasetOffer]
) -> None:
    monkeypatch.setattr(gene_sets, "uploaded_gene_lists", AsyncMock(return_value=lists))


async def test_only_an_upload_of_the_gene_list_type_is_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve_the_site(monkeypatch)

    offers = await uploaded_gene_lists("plasmodb")

    assert [(o.upload_name, o.value, o.search_name, o.parameter) for o in offers] == [
        (
            "pathfinder-uat-genelist",
            "Ud18NklEhB0wF",
            "GenesByUserDatasetGeneList",
            "geneListUserDataset",
        )
    ]


async def test_a_site_with_no_gene_list_search_reads_no_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploads = AsyncMock(return_value=_UPLOADS)
    monkeypatch.setattr(user_dataset_searches, "owned_uploads", uploads)
    monkeypatch.setattr(
        user_dataset_searches, "get_raw_searches", AsyncMock(return_value=[])
    )

    assert await uploaded_gene_lists("orthomcl") == []
    uploads.assert_not_awaited()


async def test_an_uploaded_list_is_listed_beside_the_saved_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _store(monkeypatch, _saved(1))
    _lists_on_the_site(
        monkeypatch, [_offer("pathfinder-uat-genelist", "Ud18NklEhB0wF")]
    )

    listed = returned(
        await gene_sets.list_gene_sets(agent_run_context(site_id="plasmodb")),
        GeneSetListResponse,
    )

    assert [row.id for row in listed.gene_sets] == ["gs-0"]
    assert listed.uploaded_lists == [_THE_LIST]
    assert listed.total_uploaded_lists == 1
    assert listed.next_offset is None


async def test_a_listing_returns_one_page_and_names_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _store(monkeypatch, _saved(LISTING_PAGE + 3))
    _lists_on_the_site(monkeypatch, _uploaded(LISTING_PAGE + 1))
    ctx = agent_run_context(site_id="plasmodb")

    first = returned(await gene_sets.list_gene_sets(ctx), GeneSetListResponse)
    second_result = await gene_sets.list_gene_sets(ctx, offset=LISTING_PAGE)
    second = returned(second_result, GeneSetListResponse)

    assert (len(first.gene_sets), len(first.uploaded_lists)) == (
        LISTING_PAGE,
        LISTING_PAGE,
    )
    assert (first.total_sets, first.total_uploaded_lists) == (
        LISTING_PAGE + 3,
        LISTING_PAGE + 1,
    )
    assert first.next_offset == LISTING_PAGE
    assert [row.id for row in second.gene_sets] == [
        f"gs-{n}" for n in range(LISTING_PAGE, LISTING_PAGE + 3)
    ]
    assert [row.name for row in second.uploaded_lists] == [f"upload {LISTING_PAGE}"]
    assert second.next_offset is None
    assert second.gene_sets[0].gene_count == 2
    assert [c for c in second_result.metadata if c.type == "data-gene-set-list"] == []


async def test_a_listing_names_no_gene_a_set_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _store(monkeypatch, _saved(1))
    _lists_on_the_site(
        monkeypatch, [_offer("pathfinder-uat-genelist", "Ud18NklEhB0wF")]
    )

    listed = returned(
        await gene_sets.list_gene_sets(agent_run_context(site_id="plasmodb")),
        GeneSetListResponse,
    )

    assert listed.gene_sets[0].gene_count == 2
    assert "PF3D7_0304600" not in listed.model_dump_json()


async def test_a_service_that_does_not_answer_keeps_the_saved_sets_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _store(monkeypatch, _saved(1))
    monkeypatch.setattr(
        gene_sets,
        "uploaded_gene_lists",
        AsyncMock(side_effect=VdiServiceError("VDI answered 503")),
    )

    listed = returned(
        await gene_sets.list_gene_sets(agent_run_context(site_id="plasmodb")),
        GeneSetListResponse,
    )

    assert [row.id for row in listed.gene_sets] == ["gs-0"]
    assert listed.uploaded_lists == []
    assert listed.uploads_unread is True


async def test_a_name_no_set_holds_is_refused_with_one_page_of_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _listed(*, site_id: str, user_id: UUID | None) -> list[GeneSet]:
        del site_id, user_id
        return _saved(LISTING_PAGE + 5)

    monkeypatch.setattr(_frame_gene_set, "list_stored_gene_sets", _listed)
    stated = Criterion(id="c_list", text="my list")

    with pytest.raises(ModelRetry) as refused:
        await _frame_gene_set.set_gene_set_criterion(
            agent_run_context(site_id="plasmodb"), stated, reference="missing"
        )

    message = str(refused.value)
    assert f"'set {LISTING_PAGE - 1}'" in message
    assert f"'set {LISTING_PAGE}'" not in message
    assert "5 more" in message
    assert "list_gene_sets" in message


async def test_a_refused_upload_names_one_page_of_uploads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    many = [
        OwnedUpload(vdi_id=f"id{n}", name=f"upload {n}", type_name="genelist")
        for n in range(LISTING_PAGE + 5)
    ]
    terms = [{"term": f"id{n}", "display": f"upload {n}"} for n in range(len(many))]
    parameter = next(
        p for p in _GENE_LIST.parameters or [] if p.name == "geneListUserDataset"
    )
    vocabulary = type(parameter).model_validate(
        {
            **parameter.model_dump(by_alias=True),
            "vocabulary": [[t["term"], t["display"], None] for t in terms],
        }
    )
    search = _GENE_LIST.model_copy(update={"parameters": [vocabulary]})
    monkeypatch.setattr(
        user_dataset_searches, "owned_uploads", AsyncMock(return_value=many)
    )
    monkeypatch.setattr(
        user_dataset_searches, "read_search_definition", AsyncMock(return_value=search)
    )

    with pytest.raises(ModelRetry) as refused:
        await refuse_unmatched_values(
            "plasmodb",
            search,
            CriterionCall(
                criterion_id="c_list",
                search_name="GenesByUserDatasetGeneList",
                text="my list",
                params={"geneListUserDataset": "bla"},
            ),
            [],
            frozenset(),
            AgentToolState(),
        )

    message = str(refused.value)
    assert f"id{LISTING_PAGE - 1}" in message
    assert f"id{LISTING_PAGE})" not in message
    assert "5 more" in message
