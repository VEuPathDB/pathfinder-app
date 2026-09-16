"""Per-gene composite confidence scoring.

Combines classification, ensemble frequency, and enrichment support
into a single ranked score. Pure computation - no I/O.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GeneConfidenceScore:
    """Confidence breakdown for a single gene."""

    gene_id: str
    composite_score: float
    classification_score: float
    ensemble_score: float
    enrichment_score: float


@dataclass(frozen=True, slots=True)
class GeneClassification:
    """TP/FP/FN/TN gene ID lists from a classification result."""

    tp_ids: list[str]
    fp_ids: list[str]
    fn_ids: list[str]
    tn_ids: list[str]


_CLASSIFICATION_WEIGHTS: dict[str, float] = {
    "TP": 1.0,
    "FP": -1.0,
    "FN": -0.5,
    "TN": 0.0,
}


def compute_gene_confidence(
    classification: GeneClassification,
    *,
    ensemble_scores: dict[str, float] | None = None,
    enrichment_gene_counts: dict[str, int] | None = None,
    max_enrichment_terms: int = 1,
) -> list[GeneConfidenceScore]:
    """Compute per-gene confidence scores, sorted descending by composite."""
    ens = ensemble_scores or {}
    enrich = enrichment_gene_counts or {}
    max_terms = max(max_enrichment_terms, 1)

    seen: set[str] = set()
    classified: list[tuple[str, float]] = []
    for label, ids in [
        ("TP", classification.tp_ids),
        ("FP", classification.fp_ids),
        ("FN", classification.fn_ids),
        ("TN", classification.tn_ids),
    ]:
        for gid in ids:
            if gid not in seen:
                seen.add(gid)
                classified.append((gid, _CLASSIFICATION_WEIGHTS[label]))

    results: list[GeneConfidenceScore] = []
    for gid, cls_score in classified:
        ens_score = ens.get(gid, 0.0)
        enr_score = min(enrich.get(gid, 0) / max_terms, 1.0)
        composite = (cls_score + ens_score + enr_score) / 3.0
        results.append(
            GeneConfidenceScore(
                gene_id=gid,
                composite_score=composite,
                classification_score=cls_score,
                ensemble_score=ens_score,
                enrichment_score=enr_score,
            )
        )

    results.sort(key=lambda s: s.composite_score, reverse=True)
    return results
