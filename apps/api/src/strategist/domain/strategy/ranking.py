from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping
from typing import Annotated

from pydantic import Field

from strategist.domain.comparison_facts import ComparedVariant

Weight = Annotated[int | None, Field(exclude_if=lambda weight: weight is None)]


def gene_scores(
    held: Mapping[str, Collection[str]],
    weights: Mapping[str, int],
    kept: Collection[str],
) -> dict[int, int]:
    scores = Counter(
        sum(weight for label, weight in weights.items() if gene in held[label])
        for gene in kept
    )
    return dict(sorted(scores.items(), reverse=True))


def score_rows(
    scores: Mapping[int, int], *, top: int, title: str = ""
) -> list[ComparedVariant]:
    head = f"{title}: score" if title else "Score"
    return [
        ComparedVariant(label=f"{head} {score} of {top}", gene_count=count)
        for score, count in sorted(scores.items(), reverse=True)
    ]


__all__ = ["Weight", "gene_scores", "score_rows"]
