"""The site each gene of a set lives on, read once when the set is saved."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from veupathdb.wdk import (
    WDKAnswer,
    WDKDatasetConfigIdList,
    WDKDatasetIdListContent,
    WDKRecordInstance,
    WDKSearchConfig,
    get_site,
    get_site_router,
    get_strategy_api,
    get_wdk_client,
)
from veupathdb_mcp.wdk import step_view_filters

from pathfinder.domain.gene_homes import (
    GENE_RECORD_CLASSES,
    PROTEIN_RECORD_CLASS,
    GeneHome,
    SiteKind,
    holds_genes,
)
from pathfinder.services.gene_sets.step_genes import extract_gene_id

_ORTHOMCL_PROJECT = "OrthoMCL"
_ALL = {"offset": 0, "numRecords": -1}


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


async def gene_homes(
    site_id: str,
    gene_ids: list[str],
    *,
    record_type: str | None,
    wdk_step_id: int | None,
) -> dict[str, GeneHome]:
    """Each saved id that names a gene, with its gene on the site that holds it.

    A genomics site holds its own genes. Elsewhere a step's records answer for
    its ids, and a list without a step is answered by the site's id-list search.
    Records of a class that holds no genes answer nothing.
    """
    kind = site_kind(site_id)
    if kind == "genomics":
        if (record_type or "transcript") not in GENE_RECORD_CLASSES:
            return {}
        return {gene: GeneHome(gene_id=gene, site_id=site_id) for gene in gene_ids}
    answer = (
        await _list_answer(site_id, kind, gene_ids)
        if wdk_step_id is None
        else await _step_answer(site_id, kind, wdk_step_id)
    )
    if answer is None:
        return {}
    homes = {
        saved: home
        for record in answer.records
        if (saved := extract_gene_id(record))
        and (home := _home(record, saved, site_id, kind))
    }
    return {gene: homes[gene] for gene in gene_ids if gene in homes}


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


async def _step_answer(
    site_id: str, kind: SiteKind, wdk_step_id: int
) -> WDKAnswer | None:
    api = get_strategy_api(site_id)
    filters = await step_view_filters(api, wdk_step_id)
    head = await api.get_step_answer(
        wdk_step_id,
        attributes=["primary_key"],
        pagination={"offset": 0, "numRecords": 0},
        view_filters=filters,
    )
    if not holds_genes(kind, head.meta.record_class_name):
        return None
    return await api.get_step_answer(
        wdk_step_id,
        attributes=["primary_key", *_HOME_ATTRIBUTES[kind]],
        pagination=_ALL,
        view_filters=filters,
    )


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


def _home(
    record: WDKRecordInstance, saved: str, site_id: str, kind: SiteKind
) -> GeneHome | None:
    match kind:
        case "genomics":
            return GeneHome(gene_id=saved, site_id=site_id)
        case "portal":
            home = _site_of_project(record.attribute_text("project_id"))
            return None if home is None else GeneHome(gene_id=saved, site_id=home)
        case "orthomcl":
            gene = record.attribute_text("gene_source_id")
            home = _site_of_url(record.attribute_text("gene_source_url"))
            if not gene or home is None:
                return None
            return GeneHome(gene_id=gene, site_id=home)


def _genomics_sites() -> list[tuple[str, str, str]]:
    """Each genomics site's id, project id and web domain."""
    return [
        (site.id, site.project_id, _domain(site.base_url))
        for site in get_site_router().list_sites()
        if site_kind(site.id) == "genomics"
    ]


def _site_of_project(project_id: str | None) -> str | None:
    return next((s for s, p, _ in _genomics_sites() if p == project_id), None)


def _site_of_url(url: str | None) -> str | None:
    domain = _domain(url or "")
    return next((s for s, _, d in _genomics_sites() if domain and d == domain), None)


def _domain(url: str) -> str:
    """The last two labels of a url's host, which a site keeps on every tier."""
    host = urlsplit(url).hostname or ""
    return ".".join(host.split(".")[-2:])


__all__ = [
    "ID_LIST_SEARCHES",
    "IdListSearch",
    "gene_homes",
    "site_kind",
    "sites_that_list",
]
