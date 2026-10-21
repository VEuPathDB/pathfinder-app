"""The site each gene of a set lives on, read once when the set is saved."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from veupathdb.wdk import (
    WDKAnswer,
    WDKDatasetConfigIdList,
    WDKDatasetIdListContent,
    WDKRecordInstance,
    WDKSearchConfig,
    WDKStep,
    get_site,
    get_site_router,
    get_strategy_api,
    get_wdk_client,
)
from veupathdb_mcp.wdk import view_filters_for

from pathfinder.domain.gene_homes import (
    GENE_RECORD_CLASSES,
    PROTEIN_RECORD_CLASS,
    GeneHome,
    SiteKind,
    holds_genes,
)
from pathfinder.platform.config import get_settings
from pathfinder.services.gene_sets.step_genes import (
    IncompleteAnswerError,
    dedup_ordered,
    extract_gene_id,
    refuse_above_the_cap,
)

_ORTHOMCL_PROJECT = "OrthoMCL"


@dataclass(frozen=True)
class IdListSearch:
    """The search of a site that answers a list of ids, and the parameter it reads."""

    record_type: str
    search_name: str
    param_name: str


ID_LIST_SEARCHES: dict[SiteKind, IdListSearch] = {
    "genomics": IdListSearch("transcript", "GeneByLocusTag", "ds_gene_ids"),
    "portal": IdListSearch("transcript", "GeneByLocusTag", "ds_gene_ids"),
    "orthomcl": IdListSearch(PROTEIN_RECORD_CLASS, "ByIdList", "source_ids"),
}

_HOME_ATTRIBUTES: dict[SiteKind, list[str]] = {
    "genomics": [],
    "portal": ["project_id"],
    "orthomcl": ["gene_source_id", "gene_source_url"],
}


def site_kind(site_id: str) -> SiteKind:
    """Whether a site holds its own genes, every site's genes, or ortholog groups."""
    site = get_site(site_id)
    if site.is_portal:
        return "portal"
    if site.project_id == _ORTHOMCL_PROJECT:
        return "orthomcl"
    return "genomics"


class StepGenes(CamelModel):
    model_config = ConfigDict(frozen=True)

    gene_ids: list[str]
    homes: dict[str, GeneHome]
    record_class: str


async def gene_homes(
    site_id: str,
    gene_ids: list[str],
    *,
    record_type: str | None,
) -> dict[str, GeneHome]:
    """Each id of a list that names a gene, with its gene on the site that holds it.

    A genomics site holds its own genes. Elsewhere the site's id-list search
    answers for the ids.
    """
    kind = site_kind(site_id)
    if kind == "genomics":
        if (record_type or "transcript") not in GENE_RECORD_CLASSES:
            return {}
        return {gene: GeneHome(gene_id=gene, site_id=site_id) for gene in gene_ids}
    refuse_above_the_cap(len(gene_ids))
    answer = await _list_answer(site_id, kind, gene_ids)
    homes = _homes(answer.records, site_id, kind)
    return {gene: homes[gene] for gene in gene_ids if gene in homes}


async def read_step_genes(site_id: str, step_id: int) -> StepGenes:
    step = await get_strategy_api(site_id).find_step(step_id)
    return await read_genes_of(site_id, step)


async def read_genes_of(site_id: str, step: WDKStep) -> StepGenes:
    api = get_strategy_api(site_id)
    record_class = step.record_class_name or ""
    count = step.estimated_size
    if count is None:
        count = await api.get_step_count(step.id)
    refuse_above_the_cap(count)
    if count == 0:
        return StepGenes(gene_ids=[], homes={}, record_class=record_class)
    kind = site_kind(site_id)
    homed = holds_genes(kind, record_class)
    answer = await api.get_step_answer(
        step.id,
        attributes=["primary_key", *(_HOME_ATTRIBUTES[kind] if homed else [])],
        pagination={"offset": 0, "numRecords": get_settings().step_genes_cap},
        view_filters=view_filters_for(record_class),
    )
    counted = answer.meta.records_returned()
    refuse_above_the_cap(counted)
    if counted > len(answer.records):
        raise IncompleteAnswerError(counted, len(answer.records))
    gene_ids = dedup_ordered(
        [gene for record in answer.records if (gene := extract_gene_id(record))]
    )
    homes = _homes(answer.records, site_id, kind) if homed else {}
    return StepGenes(gene_ids=gene_ids, homes=homes, record_class=record_class)


def sites_that_list(site_id: str, homes: Mapping[str, GeneHome]) -> list[str]:
    """The names of the sites a set lists on: its own, then the sites that hold
    its genes, the portal and OrthoMCL."""
    homed = {home.site_id for home in homes.values()}
    listed = [
        site.id
        for site in get_site_router().list_sites()
        if site.id != site_id
        and homed
        and (site.id in homed or site_kind(site.id) != "genomics")
    ]
    return [get_site(s).name for s in [site_id, *listed]]


async def _list_answer(site_id: str, kind: SiteKind, gene_ids: list[str]) -> WDKAnswer:
    search = ID_LIST_SEARCHES[kind]
    dataset_id = await get_strategy_api(site_id).create_dataset(
        WDKDatasetConfigIdList(
            source_type="idList",
            source_content=WDKDatasetIdListContent(ids=gene_ids),
        )
    )
    return await get_wdk_client(site_id).run_search_report(
        search.record_type,
        search.search_name,
        WDKSearchConfig(parameters={search.param_name: str(dataset_id)}),
        {
            "attributes": ["primary_key", *_HOME_ATTRIBUTES[kind]],
            "pagination": {"offset": 0, "numRecords": -1},
        },
    )


@dataclass(frozen=True)
class _GenomicsSites:
    by_project: dict[str, str]
    by_domain: dict[str, str]


def _genomics_sites() -> _GenomicsSites:
    by_project: dict[str, str] = {}
    by_domain: dict[str, str] = {}
    for site in get_site_router().list_sites():
        if site_kind(site.id) == "genomics":
            by_project.setdefault(site.project_id, site.id)
            by_domain.setdefault(_domain(site.base_url), site.id)
    return _GenomicsSites(by_project=by_project, by_domain=by_domain)


def _homes(
    records: Sequence[WDKRecordInstance], site_id: str, kind: SiteKind
) -> dict[str, GeneHome]:
    sites = _genomics_sites()
    return {
        saved: home
        for record in records
        if (saved := extract_gene_id(record))
        and (home := _home(record, saved, site_id, kind, sites))
    }


def _home(
    record: WDKRecordInstance,
    saved: str,
    site_id: str,
    kind: SiteKind,
    sites: _GenomicsSites,
) -> GeneHome | None:
    match kind:
        case "genomics":
            return GeneHome(gene_id=saved, site_id=site_id)
        case "portal":
            home = sites.by_project.get(record.attribute_text("project_id") or "")
            return None if home is None else GeneHome(gene_id=saved, site_id=home)
        case "orthomcl":
            gene = record.attribute_text("gene_source_id")
            domain = _domain(record.attribute_text("gene_source_url") or "")
            home = sites.by_domain.get(domain) if domain else None
            if not gene or home is None:
                return None
            return GeneHome(gene_id=gene, site_id=home)


def _domain(url: str) -> str:
    """The last two labels of a url's host, which a site keeps on every tier."""
    host = urlsplit(url).hostname or ""
    return ".".join(host.split(".")[-2:])


__all__ = [
    "ID_LIST_SEARCHES",
    "IdListSearch",
    "StepGenes",
    "gene_homes",
    "read_genes_of",
    "read_step_genes",
    "site_kind",
    "sites_that_list",
]
