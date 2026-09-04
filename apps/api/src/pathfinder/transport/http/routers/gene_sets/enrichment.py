"""Enrichment analysis over a stored gene set."""

from assistant_core.platform.types import JSONObject
from fastapi import APIRouter

from pathfinder.platform.errors import InternalError
from pathfinder.transport.http.deps import CurrentUser
from pathfinder.transport.http.schemas.gene_sets import GeneSetEnrichRequest

from ._shared import NEEDS_WDK_LOGIN, gene_set_service, not_found

router = APIRouter()


@router.post("/{gene_set_id}/enrich", dependencies=NEEDS_WDK_LOGIN)
async def enrich_gene_set(
    gene_set_id: str,
    request: GeneSetEnrichRequest,
    user_id: CurrentUser,
) -> list[JSONObject]:
    """Run enrichment analysis on a gene set."""
    try:
        results = await gene_set_service().run_enrichment(
            user_id, gene_set_id, request.enrichment_types
        )
    except KeyError as exc:
        raise not_found(exc) from exc
    except RuntimeError as exc:
        raise InternalError(
            title="Enrichment analysis failed", detail=str(exc)
        ) from exc
    return [r.model_dump(by_alias=True) for r in results]
