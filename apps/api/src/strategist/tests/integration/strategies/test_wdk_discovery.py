from __future__ import annotations

import pytest
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import vocab_keys
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKEnumParam
from veupathdb_mcp.catalog import get_discovery_service

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_ORGANISM = "Plasmodium falciparum 3D7"


async def test_record_types_include_transcript(wdk_session: None) -> None:
    del wdk_session
    record_types = await get_discovery_service().get_record_types("plasmodb")
    assert "transcript" in {rt.url_segment for rt in record_types}


async def test_searches_include_genes_by_text_and_taxon(
    wdk_session: None,
) -> None:
    del wdk_session
    searches = await get_discovery_service().get_searches("plasmodb", "transcript")
    url_segments = {s.url_segment for s in searches}
    assert "GenesByText" in url_segments
    assert "GenesByTaxon" in url_segments


async def test_genes_by_taxon_organism_vocab_contains_pf3d7(
    wdk_session: None,
) -> None:
    del wdk_session
    ctx = SearchContext(
        site_id="plasmodb", record_type="transcript", search_name="GenesByTaxon"
    )
    response = await get_discovery_service().get_search_details(ctx, expand_params=True)
    params = response.search_data.parameters or []
    organism = next(p for p in params if p.name == "organism")
    assert isinstance(organism, WDKEnumParam)
    assert organism.type == "multi-pick-vocabulary"
    assert _ORGANISM in vocab_keys(organism.vocabulary)


async def test_genes_by_text_exposes_its_text_params(
    wdk_session: None,
) -> None:
    del wdk_session
    ctx = SearchContext(
        site_id="plasmodb", record_type="transcript", search_name="GenesByText"
    )
    response = await get_discovery_service().get_search_details(ctx, expand_params=True)
    names = {p.name for p in (response.search_data.parameters or [])}
    assert "text_expression" in names
    assert "text_fields" in names


async def test_unknown_search_raises(wdk_session: None) -> None:
    del wdk_session
    ctx = SearchContext(
        site_id="plasmodb", record_type="transcript", search_name="NotARealSearch"
    )
    with pytest.raises(WDKError) as refusal:
        await get_discovery_service().get_search_details(ctx, expand_params=True)
    assert refusal.value.status == 404
