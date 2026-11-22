"""A range facet of a filter parameter binds on the live site and narrows the count."""

from __future__ import annotations

import pytest
from pydantic import JsonValue
from veupathdb_mcp.catalog import (
    ParamIntent,
    WDKFilterReads,
    resolve_params_with_intent,
    wdk_fetch_at,
)

from strategist.services.strategies.wdk_counts import count_bound_criterion

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_SEARCH = "GenesByVariantCharacteristics"
_PARAM = "gene_variant_stats"
# The filter's vocabulary depends on the organism, and no organism selects no genes.
_ORGANISM = {
    "plasmodb": "Plasmodium falciparum 3D7",
    "toxodb": "Toxoplasma gondii ME49",
}
_RARE_VARIANTS: JsonValue = [
    {"field": "max_minor_allele_frequency", "value": {"max": 0.05}}
]


async def _count(site_id: str, stated: dict[str, JsonValue]) -> int | None:
    resolved = await resolve_params_with_intent(
        fetch_at=wdk_fetch_at(site_id, "transcript", _SEARCH),
        filter_reads=WDKFilterReads(site_id, "transcript", _SEARCH),
        intent=ParamIntent(),
        search_name=_SEARCH,
        stated={"organism_select_none": [_ORGANISM[site_id]], **stated},
    )
    return await count_bound_criterion(site_id, "transcript", _SEARCH, resolved.params)


@pytest.mark.parametrize("site_id", ["plasmodb", "toxodb"])
async def test_a_maximum_allele_frequency_narrows_the_genes(
    wdk_session: None, site_id: str
) -> None:
    del wdk_session
    every = await _count(site_id, {})
    rare = await _count(site_id, {_PARAM: _RARE_VARIANTS})

    assert every is not None
    assert rare is not None
    assert 0 < rare < every
