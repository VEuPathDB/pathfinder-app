"""Ensemble gene scoring - frequency across multiple gene sets."""

from collections import Counter
from typing import TypedDict


class EnsembleScore(TypedDict):
    """A single gene's ensemble score."""

    geneId: str
    frequency: float
    count: int
    total: int
    inPositives: bool


def compute_ensemble_scores(
    gene_sets: list[list[str]],
    positive_controls: list[str] | None = None,
) -> list[EnsembleScore]:
    """Score genes by how frequently they appear across gene sets.

    Returns a list of EnsembleScore dicts sorted by frequency (desc),
    then gene ID (asc).
    """
    if not gene_sets:
        return []

    total = len(gene_sets)
    counts: Counter[str] = Counter()
    for gs in gene_sets:
        counts.update(gs)

    positives = set(positive_controls) if positive_controls else set()

    scores: list[EnsembleScore] = [
        EnsembleScore(
            geneId=gene_id,
            frequency=count / total,
            count=count,
            total=total,
            inPositives=gene_id in positives,
        )
        for gene_id, count in counts.items()
    ]
    scores.sort(key=lambda r: (-r["frequency"], r["geneId"]))
    return scores
