"""Custom gene-set enrichment endpoint for experiments."""

from fastapi import APIRouter

from pathfinder.services.enrichment.custom import (
    CustomEnrichmentResult,
    run_custom_enrichment,
)
from pathfinder.transport.http.deps import CurrentUser, ExperimentDep
from pathfinder.transport.http.schemas.experiments import CustomEnrichRequest

router = APIRouter()


@router.post("/{experiment_id}/custom-enrich")
async def custom_enrichment(
    exp: ExperimentDep,
    request: CustomEnrichRequest,
    user_id: CurrentUser,
) -> CustomEnrichmentResult:
    """Test enrichment of a custom gene set against the experiment results."""
    return run_custom_enrichment(exp, request.gene_ids, request.gene_set_name)
