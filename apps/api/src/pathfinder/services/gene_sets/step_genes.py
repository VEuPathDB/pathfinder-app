"""The gene ids a WDK step holds."""

from veupathdb.domain.search import SearchContext
from veupathdb.wdk import StrategyAPI, WDKRecordInstance, get_strategy_api
from veupathdb_mcp.catalog import get_search_parameters

from pathfinder.services.gene_sets.operations import dedup_ordered

# A transcript record names its gene beside its own id. A set holds the gene id.
_GENE_ID_PARTS = ("gene_source_id", "source_id")


async def step_gene_ids(site_id: str, step_id: int) -> list[str]:
    """Every gene id a WDK step holds, on the site that runs it."""
    return await fetch_all_gene_ids(get_strategy_api(site_id), step_id)


async def fetch_all_gene_ids(
    api: StrategyAPI,
    step_id: int,
    batch_size: int = 1000,
) -> list[str]:
    """Fetch all gene IDs from a WDK step using paginated standard report."""
    all_ids: list[str] = []
    offset = 0

    while True:
        answer = await api.get_step_answer(
            step_id,
            attributes=["primary_key"],
            pagination={"offset": offset, "numRecords": batch_size},
        )

        records = answer.records
        if not records:
            break

        for record in records:
            gene_id = extract_gene_id(record)
            if gene_id:
                all_ids.append(gene_id)

        offset += len(records)
        if offset >= answer.meta.records_returned():
            break

    return dedup_ordered(all_ids)


def extract_gene_id(record: WDKRecordInstance) -> str | None:
    """The gene id a record's primary key names, or its first part."""
    for name in _GENE_ID_PARTS:
        for part in record.id:
            if part.name == name and part.value:
                return part.value
    if record.id:
        return record.id[0].value or None
    return None


async def visible_parameter_names(
    site_id: str, *, record_type: str, search_name: str
) -> frozenset[str]:
    """The parameters of a search that WDK shows a user.

    A hidden parameter is WDK's own default and records no choice of the
    researcher, so a save keeps the visible ones.
    """
    found = await get_search_parameters(
        SearchContext(site_id=site_id, search_name=search_name, record_type=record_type)
    )
    return frozenset(p.name for p in found.parameters if p.is_visible)
