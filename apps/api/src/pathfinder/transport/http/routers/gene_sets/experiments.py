"""The evaluations a gene set has been through."""

from fastapi import APIRouter

from pathfinder.services.experiment.store import get_experiment_store
from pathfinder.services.experiment.types import Experiment
from pathfinder.transport.http.deps import CurrentUser

from ._shared import gene_set_service

router = APIRouter()


@router.get("/{gene_set_id}/experiments")
async def list_gene_set_experiments(
    gene_set_id: str,
    user_id: CurrentUser,
) -> list[Experiment]:
    """List this user's experiments on one gene set, newest first."""
    await gene_set_service().get_for_user(user_id, gene_set_id)
    return await get_experiment_store().alist_for_gene_set(gene_set_id, user_id)
