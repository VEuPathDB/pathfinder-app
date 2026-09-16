"""Reverse search - rank gene sets by how well they recover positive genes.

Given a set of known-positive gene IDs, score each candidate gene set on
recall, precision, and F1 using pure set intersection.  No WDK calls needed
because the gene IDs are already materialised.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GeneSetCandidate:
    """A gene set to evaluate against the positive controls."""

    id: str
    name: str
    gene_ids: list[str]
    search_name: str | None = None


@dataclass(frozen=True, slots=True)
class RankedResult:
    """A scored gene set with classification metrics."""

    gene_set_id: str
    name: str
    search_name: str | None
    recall: float
    precision: float
    f1: float
    estimated_size: int
    overlap_count: int


def rank_gene_sets_by_recall(
    gene_sets: list[GeneSetCandidate],
    positive_ids: list[str],
    negative_ids: list[str] | None = None,
) -> list[RankedResult]:
    """Rank gene sets by recall of *positive_ids*, then by F1 descending.

    :param gene_sets: Candidate gene sets to evaluate.
    :param positive_ids: Known-positive gene IDs to recover.
    :param negative_ids: Optional negative controls (used for precision).
    :returns: Sorted list of ranked results (best first).
    """
    if not gene_sets:
        return []

    pos = set(positive_ids)
    neg = set(negative_ids) if negative_ids else set[str]()
    results: list[RankedResult] = []

    for gs in gene_sets:
        gs_ids = set(gs.gene_ids)
        overlap = gs_ids & pos
        overlap_count = len(overlap)
        estimated_size = len(gs_ids)

        recall = overlap_count / len(pos) if pos else 0.0

        # Precision: of all results, how many are true positives?
        # If negatives are provided, a result that's neither positive nor
        # negative is ignored (unknown).  Without negatives, every non-positive
        # result is treated as a false positive.
        neg_hits = len(gs_ids & neg) if neg else estimated_size - overlap_count
        tp = overlap_count
        fp = neg_hits if neg else estimated_size - overlap_count
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0

        f1_denom = precision + recall
        f1 = (2 * precision * recall / f1_denom) if f1_denom > 0 else 0.0

        results.append(
            RankedResult(
                gene_set_id=gs.id,
                name=gs.name,
                search_name=gs.search_name,
                recall=recall,
                precision=precision,
                f1=f1,
                estimated_size=estimated_size,
                overlap_count=overlap_count,
            )
        )

    results.sort(key=lambda r: (-r.recall, -r.f1))
    return results
