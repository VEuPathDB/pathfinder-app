"""Gene search and resolve endpoints."""

from assistant_core.platform.pydantic_base import CamelModel
from fastapi import APIRouter
from pydantic import Field
from veupathdb_mcp.gene_lookup import (
    list_organisms,
    lookup_genes_by_text,
    resolve_gene_ids,
)

router = APIRouter(prefix="/api/v1/sites", tags=["sites"])


class GeneSearchResultResponse(CamelModel):
    gene_id: str
    display_name: str = ""
    organism: str = ""
    product: str = ""
    gene_name: str = ""
    gene_type: str = ""
    location: str = ""
    matched_fields: list[str] = Field(default_factory=list)


class GeneSearchResponse(CamelModel):
    results: list[GeneSearchResultResponse]
    total_count: int
    suggested_organisms: list[str] = Field(default_factory=list)


class GeneResolveRequest(CamelModel):
    gene_ids: list[str]


class ResolvedGeneResponse(CamelModel):
    gene_id: str
    display_name: str = ""
    organism: str = ""
    product: str = ""
    gene_name: str = ""
    gene_type: str = ""
    location: str = ""


class GeneResolveResponse(CamelModel):
    resolved: list[ResolvedGeneResponse]
    unresolved: list[str]


class OrganismsResponse(CamelModel):
    organisms: list[str]


@router.get("/{site_id}/organisms", response_model=OrganismsResponse)
async def get_organisms(site_id: str) -> OrganismsResponse:
    orgs = await list_organisms(site_id)
    return OrganismsResponse(organisms=orgs)


@router.get("/{site_id}/genes/search", response_model=GeneSearchResponse)
async def search_genes(
    site_id: str,
    q: str = "",
    organism: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> GeneSearchResponse:
    result = await lookup_genes_by_text(
        site_id,
        q,
        organism=organism or None,
        limit=limit,
        offset=offset,
    )
    return GeneSearchResponse(
        results=[
            GeneSearchResultResponse(
                gene_id=r.gene_id,
                display_name=r.display_name or r.product or r.gene_id,
                organism=r.organism,
                product=r.product,
                gene_name=r.gene_name,
                gene_type=r.gene_type,
                location=r.location,
                matched_fields=r.matched_fields or [],
            )
            for r in result.records
        ],
        total_count=result.total_count,
        suggested_organisms=result.suggested_organisms or [],
    )


@router.post("/{site_id}/genes/resolve", response_model=GeneResolveResponse)
async def resolve_genes(
    site_id: str,
    payload: GeneResolveRequest,
) -> GeneResolveResponse:
    result = await resolve_gene_ids(site_id, payload.gene_ids)
    resolved_ids: set[str] = set()
    resolved: list[ResolvedGeneResponse] = []
    for rec in result.records:
        if not rec.gene_id:
            continue
        resolved_ids.add(rec.gene_id)
        resolved.append(
            ResolvedGeneResponse(
                gene_id=rec.gene_id,
                display_name=rec.product or rec.gene_id,
                organism=rec.organism,
                product=rec.product,
                gene_name=rec.gene_name,
                gene_type=rec.gene_type,
                location=rec.location,
            ),
        )
    unresolved = [gid for gid in payload.gene_ids if gid not in resolved_ids]
    return GeneResolveResponse(resolved=resolved, unresolved=unresolved)
