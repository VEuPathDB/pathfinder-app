from __future__ import annotations

from veupathdb.domain import SearchContext
from veupathdb_mcp.catalog import (
    eda_backed_search,
    get_discovery_service,
    list_eda_backed,
)

_RECORD_TYPE = "transcript"


async def _preset_dataset(site_id: str, search_name: str) -> str | None:
    details = await get_discovery_service().get_search_details(
        SearchContext(site_id, _RECORD_TYPE, search_name)
    )
    described = eda_backed_search(details.search_data)
    return None if described is None else described.default_dataset_id


async def dataset_subset_search(site_id: str, dataset_id: str) -> str | None:
    for listed in await list_eda_backed(site_id):
        if listed.is_compute_backed or not listed.reads_the_spec:
            continue
        if await _preset_dataset(site_id, listed.search_name) == dataset_id:
            return listed.search_name
    return None
