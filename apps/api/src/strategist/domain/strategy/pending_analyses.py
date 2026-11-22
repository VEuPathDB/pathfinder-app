"""The criteria waiting for the Lead's EDA tools."""

from strategist.domain.strategy.operational_spec import Criterion, OperationalSpec


def pending_analyses(spec: OperationalSpec | None) -> list[Criterion]:
    """Every criterion waiting for the Lead's EDA tools, in spec order."""
    if spec is None:
        return []
    return [criterion for criterion in spec.criteria if criterion.pending_analysis]
