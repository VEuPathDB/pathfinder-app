"""Publishing a gene set to the researcher's VEuPathDB workspace."""

from fastapi import APIRouter

from pathfinder.services.gene_sets.vdi import (
    VdiPublication,
    VdiPublicationRequest,
    VdiPublicationStatus,
    publish_to_vdi,
    vdi_publication_status,
)
from pathfinder.transport.http.deps import CurrentUser

from ._shared import NEEDS_WDK_LOGIN, gene_set_service

router = APIRouter()


@router.post(
    "/{gene_set_id}/vdi-publication", status_code=201, dependencies=NEEDS_WDK_LOGIN
)
async def publish_gene_set_to_vdi(
    gene_set_id: str,
    body: VdiPublicationRequest,
    user_id: CurrentUser,
) -> VdiPublication:
    """Publish a gene set as a user dataset on the site it was built against."""
    return await publish_to_vdi(
        gene_set_service(),
        user_id,
        gene_set_id,
        name=body.name,
        visibility=body.visibility,
    )


@router.get("/{gene_set_id}/vdi-publication", dependencies=NEEDS_WDK_LOGIN)
async def get_gene_set_vdi_publication(
    gene_set_id: str,
    user_id: CurrentUser,
) -> VdiPublicationStatus:
    """Read where a published gene set stands on the site that holds it."""
    return await vdi_publication_status(gene_set_service(), user_id, gene_set_id)
