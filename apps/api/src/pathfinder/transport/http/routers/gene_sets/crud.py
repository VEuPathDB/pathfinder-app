"""Gene-set create, list, retake, delete, export and import."""

import re
from typing import Literal, cast

from fastapi import APIRouter, Query, Request
from veupathdb.errors import ValidationError
from veupathdb_mcp.wdk.gene_set_steps import GeneSetWdkContext

from pathfinder.platform.security import limiter
from pathfinder.services.export import get_export_service
from pathfinder.transport.http.deps import CurrentUser, SiteIdQuery
from pathfinder.transport.http.schemas.gene_sets import (
    CreateGeneSetRequest,
    GeneSetExportResponse,
    GeneSetImportRequest,
    GeneSetResponse,
)

from ._shared import NEEDS_WDK_LOGIN, gene_set_service, not_found, to_response

router = APIRouter()

_ID_SPLIT_RE = re.compile(r"[\s,;\t]+")


def _parse_gene_id_blob(raw: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for tok in _ID_SPLIT_RE.split(raw):
        cleaned = tok.strip().strip('"').strip("'")
        if cleaned == "" or cleaned.lower() == "gene_id":
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


@router.post("", status_code=201, dependencies=NEEDS_WDK_LOGIN)
@limiter.limit("30/minute")
async def create_gene_set(
    request: Request,
    body: CreateGeneSetRequest,
    user_id: CurrentUser,
) -> GeneSetResponse:
    """Create a new gene set."""
    gs = await gene_set_service().create(
        user_id=user_id,
        name=body.name,
        site_id=body.site_id,
        gene_ids=body.gene_ids,
        source=body.source,
        wdk=GeneSetWdkContext(
            wdk_strategy_id=body.wdk_strategy_id,
            wdk_step_id=body.wdk_step_id,
            search_name=body.search_name,
            record_type=body.record_type,
            parameters=body.parameters,
        ),
    )
    return to_response(gs)


@router.get("")
async def list_gene_sets(
    user_id: CurrentUser,
    site_id: SiteIdQuery = None,
) -> list[GeneSetResponse]:
    """List all gene sets for the current user, optionally filtered by site."""
    sets = await gene_set_service().list_for_user(user_id, site_id=site_id)
    return [to_response(gs) for gs in sets]


@router.post("/{gene_set_id}/retake", dependencies=NEEDS_WDK_LOGIN)
async def retake_gene_set(
    gene_set_id: str,
    user_id: CurrentUser,
) -> GeneSetResponse:
    """Replace a gene set's genes with what its source strategy holds now."""
    try:
        gs = await gene_set_service().retake_from_source(user_id, gene_set_id)
    except KeyError as exc:
        raise not_found(exc) from exc
    return to_response(gs)


@router.delete("/{gene_set_id}")
async def delete_gene_set(
    gene_set_id: str,
    user_id: CurrentUser,
) -> dict[str, bool]:
    """Delete a gene set."""
    try:
        await gene_set_service().delete(user_id, gene_set_id)
    except KeyError as exc:
        raise not_found(exc) from exc
    return {"ok": True}


@router.post("/{gene_set_id}/export")
@limiter.limit("30/minute")
async def export_gene_set_endpoint(
    request: Request,
    gene_set_id: str,
    user_id: CurrentUser,
    fmt: str = Query("csv", alias="format"),
) -> GeneSetExportResponse:
    """Export a gene set as CSV or TXT. Returns a short-lived download URL."""
    del request
    if fmt not in ("csv", "txt"):
        msg = "format must be 'csv' or 'txt'"
        raise ValidationError(title=msg)
    try:
        gs = await gene_set_service().get_for_user(user_id, gene_set_id)
    except KeyError as exc:
        raise not_found(exc) from exc
    svc = get_export_service()
    result = await svc.export_gene_set(gs, cast("Literal['csv', 'txt']", fmt))
    return GeneSetExportResponse(
        export_id=result.export_id,
        filename=result.filename,
        content_type=result.content_type,
        url=result.url,
    )


@router.post("/import", status_code=201)
@limiter.limit("30/minute")
async def import_gene_set(
    request: Request,
    body: GeneSetImportRequest,
    user_id: CurrentUser,
) -> GeneSetResponse:
    """Create a gene set from a raw pasted text blob (CSV/TSV/newline list)."""
    del request
    ids = _parse_gene_id_blob(body.raw_text)
    if len(ids) == 0:
        msg = "No gene IDs parsed from input"
        raise ValidationError(title=msg)
    gs = await gene_set_service().create(
        user_id=user_id,
        name=body.name,
        site_id=body.site_id,
        gene_ids=ids,
        source="paste",
    )
    return to_response(gs)
