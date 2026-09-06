"""Trial metric extraction for parameter sweeps."""

from dataclasses import dataclass

from veupathdb_mcp.controls.control_types import ControlTestResult


@dataclass(frozen=True, slots=True)
class TrialMetrics:
    """Intermediate metrics extracted from a WDK result."""

    recall: float | None
    fpr: float | None
    estimated_size: int | None
    positive_hits: int | None
    negative_hits: int | None


def _extract_trial_metrics(wdk_result: ControlTestResult) -> TrialMetrics:
    """Extract recall, FPR, result count, and hit counts from a control-test result."""
    pos = wdk_result.positive
    neg = wdk_result.negative

    return TrialMetrics(
        recall=pos.recall if pos else None,
        fpr=neg.false_positive_rate if neg else None,
        estimated_size=wdk_result.target.estimated_size,
        positive_hits=pos.intersection_count if pos else None,
        negative_hits=neg.intersection_count if neg else None,
    )
