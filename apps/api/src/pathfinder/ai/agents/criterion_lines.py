"""What a criterion runs, as FRAME's workspace and the Lead's pins print it."""

from __future__ import annotations

from pathfinder.domain.strategy.operational_spec import Criterion

__all__ = ["criterion_label", "criterion_runs"]


def criterion_runs(criterion: Criterion) -> str:
    """What the criterion runs, or what realizes it, after its arrow."""
    if criterion.analysis is not None:
        return (
            "analysis workflow, BOUND: keep it; do not re-bind, drop, or restate "
            "this comparison with another search"
        )
    if criterion.pending_analysis:
        return (
            f"analysis workflow on dataset {criterion.needs_analysis_on}, WAITING: "
            f"keep it in the structure; the Lead builds it"
        )
    saved = criterion.saved_strategy_ref
    return criterion.search_name or (saved.label if saved is not None else "(UNBOUND)")


def criterion_label(criterion: Criterion, width: int) -> str:
    """The words a criterion is read by: an analysis's own words, in full."""
    if criterion.analysis is not None:
        return criterion.analysis.words
    return criterion.text[:width]
