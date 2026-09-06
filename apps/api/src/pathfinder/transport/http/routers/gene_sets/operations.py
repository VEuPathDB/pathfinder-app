"""Set algebra, reverse search and ensemble scoring over stored gene sets."""

from fastapi import APIRouter
from veupathdb.errors import ValidationError

from pathfinder.services.gene_sets.ensemble import (
    EnsembleScore,
    compute_ensemble_scores,
)
from pathfinder.services.gene_sets.reverse_search import (
    GeneSetCandidate,
    rank_gene_sets_by_recall,
)
from pathfinder.transport.http.deps import CurrentUser
from pathfinder.transport.http.schemas.gene_sets import (
    EnsembleScoringRequest,
    GeneSetResponse,
    ReverseSearchRequest,
    ReverseSearchResultItem,
    SetOperationRequest,
)

from ._shared import gene_set_service, not_found, to_response

router = APIRouter()


@router.post("/operations")
async def set_operations(
    request: SetOperationRequest,
    user_id: CurrentUser,
) -> GeneSetResponse:
    """Perform set operations (intersect, union, minus) between two gene sets."""
    try:
        gs = await gene_set_service().perform_set_operation(
            user_id=user_id,
            set_a_id=request.set_a_id,
            set_b_id=request.set_b_id,
            operation=request.operation,
            name=request.name,
        )
    except KeyError as exc:
        raise not_found(exc) from exc
    except ValueError as exc:
        raise ValidationError(title="Invalid operation", detail=str(exc)) from exc
    return to_response(gs)


@router.post("/reverse-search")
async def reverse_search(
    body: ReverseSearchRequest,
    user_id: CurrentUser,
) -> list[ReverseSearchResultItem]:
    """Rank the user's gene sets by how well they recover the given positive genes."""
    sets = await gene_set_service().list_for_user(user_id, site_id=body.site_id)
    candidates = [
        GeneSetCandidate(
            id=gs.id,
            name=gs.name,
            gene_ids=gs.gene_ids,
            search_name=gs.search_name,
        )
        for gs in sets
    ]
    ranked = rank_gene_sets_by_recall(
        candidates,
        body.positive_gene_ids,
        body.negative_gene_ids,
    )
    return [
        ReverseSearchResultItem(
            gene_set_id=r.gene_set_id,
            name=r.name,
            search_name=r.search_name,
            recall=r.recall,
            precision=r.precision,
            f1=r.f1,
            estimated_size=r.estimated_size,
            overlap_count=r.overlap_count,
        )
        for r in ranked
    ]


@router.post("/ensemble")
async def ensemble_scoring(
    body: EnsembleScoringRequest,
    user_id: CurrentUser,
) -> list[EnsembleScore]:
    """Score genes by frequency across multiple gene sets."""
    service = gene_set_service()
    gene_sets: list[list[str]] = []
    for gs_id in body.gene_set_ids:
        try:
            gs = await service.get_for_user(user_id, gs_id)
        except KeyError as exc:
            raise not_found(exc) from exc
        gene_sets.append(gs.gene_ids)

    return compute_ensemble_scores(gene_sets, body.positive_controls)
