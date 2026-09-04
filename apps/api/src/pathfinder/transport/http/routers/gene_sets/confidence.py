"""Per-gene composite confidence scoring."""

from fastapi import APIRouter

from pathfinder.services.gene_sets.confidence import (
    GeneClassification,
    compute_gene_confidence,
)
from pathfinder.transport.http.schemas.gene_sets import (
    GeneConfidenceRequest,
    GeneConfidenceScoreResponse,
)

router = APIRouter()


@router.post("/confidence")
async def gene_confidence(
    body: GeneConfidenceRequest,
) -> list[GeneConfidenceScoreResponse]:
    """Compute per-gene composite confidence scores from classification data."""
    scores = compute_gene_confidence(
        GeneClassification(
            tp_ids=body.tp_ids,
            fp_ids=body.fp_ids,
            fn_ids=body.fn_ids,
            tn_ids=body.tn_ids,
        ),
        ensemble_scores=body.ensemble_scores,
        enrichment_gene_counts=body.enrichment_gene_counts,
        max_enrichment_terms=body.max_enrichment_terms,
    )
    return [
        GeneConfidenceScoreResponse(
            gene_id=s.gene_id,
            composite_score=s.composite_score,
            classification_score=s.classification_score,
            ensemble_score=s.ensemble_score,
            enrichment_score=s.enrichment_score,
        )
        for s in scores
    ]
