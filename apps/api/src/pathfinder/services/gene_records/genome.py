"""The genome one gene record names, by the full organism name the site's catalog holds."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from veupathdb.errors import WDKError
from veupathdb.wdk import StrategyAPI, WDKRecordInstance, get_site, get_strategy_api
from veupathdb_mcp.wdk import order_primary_key

from pathfinder.services.gene_records.read import (
    GENE_RECORD_TYPE,
    PlainText,
    UnknownGeneRecordError,
    gene_record_type,
)

GENOME_ATTRIBUTE = "organism_full"
_NOT_FOUND_STATUS = 404


class _RecordGenome(BaseModel):
    model_config = ConfigDict(extra="ignore")

    organism_full: PlainText = Field(min_length=1)


def genome_of(record: WDKRecordInstance) -> str:
    return _RecordGenome.model_validate(record.attributes).organism_full


async def read_gene_genome(site_id: str, gene_id: str) -> str:
    return await read_the_gene_genome(get_strategy_api(site_id), site_id, gene_id)


async def read_the_gene_genome(api: StrategyAPI, site_id: str, gene_id: str) -> str:
    declared = await gene_record_type(api, site_id)
    key = order_primary_key(
        [{"name": "source_id", "value": gene_id}],
        list(declared.primary_key_refs),
        {"project_id": get_site(site_id).project_id},
    )
    try:
        record = await api.get_single_record(
            GENE_RECORD_TYPE, key, attributes=[GENOME_ATTRIBUTE], tables=[]
        )
    except WDKError as refused:
        if refused.status != _NOT_FOUND_STATUS:
            raise
        raise UnknownGeneRecordError(site_id, gene_id) from refused
    return genome_of(record)
