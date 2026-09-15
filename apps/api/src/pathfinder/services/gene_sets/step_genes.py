"""The gene ids a WDK step holds."""

from veupathdb.wdk import StrategyAPI, WDKRecordInstance, get_strategy_api


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

    return all_ids


def extract_gene_id(record: WDKRecordInstance) -> str | None:
    """Extract gene ID from a WDK record's primary key."""
    for part in record.id:
        if part.name in ("source_id", "gene_source_id") and part.value:
            return part.value
    if record.id:
        return record.id[0].value or None
    return None
