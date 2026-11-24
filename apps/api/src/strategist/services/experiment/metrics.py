"""Metrics engine for computing exhaustive classification metrics.

Computes all standard binary classification metrics from the raw
intersection counts returned by :func:`run_positive_negative_controls`.
"""

import math
from collections.abc import Callable

from veupathdb_mcp.controls import (
    ControlTestResult,
)

from strategist.domain.unread import Unread
from strategist.services.experiment.types import (
    ConfusionMatrix,
    ExperimentMetrics,
)


def compute_confusion_matrix(
    *,
    positive_hits: int,
    total_positives: int,
    negative_hits: int,
    total_negatives: int,
) -> ConfusionMatrix:
    """Derive a confusion matrix from control-test intersection counts.

    :param positive_hits: Number of positive controls found in results (TP).
    :param total_positives: Total positive controls provided.
    :param negative_hits: Number of negative controls found in results (FP).
    :param total_negatives: Total negative controls provided.
    :returns: Populated confusion matrix.
    """
    tp = positive_hits
    fn = total_positives - positive_hits
    fp = negative_hits
    tn = total_negatives - negative_hits
    return ConfusionMatrix(
        true_positives=max(tp, 0),
        false_positives=max(fp, 0),
        true_negatives=max(tn, 0),
        false_negatives=max(fn, 0),
    )


NO_POSITIVES = Unread(reason="no positive controls")
NO_NEGATIVES = Unread(reason="no negative controls")
_NONE_RETURNED = Unread(reason="the result holds no control")
_ALL_RETURNED = Unread(reason="the result holds every control")


def _ratio(part: int, whole: int, empty: Unread) -> float | Unread:
    return part / whole if whole > 0 else empty


def _both(
    first: float | Unread,
    second: float | Unread,
    joined: Callable[[float, float], float],
) -> float | Unread:
    match first:
        case Unread():
            return first
    match second:
        case Unread():
            return second
    return joined(first, second)


def _f1(precision: float, sensitivity: float) -> float:
    total = precision + sensitivity
    return 2 * precision * sensitivity / total if total > 0 else 0.0


def _mcc(cm: ConfusionMatrix) -> float | Unread:
    tp, fp, tn, fn = (
        cm.true_positives,
        cm.false_positives,
        cm.true_negatives,
        cm.false_negatives,
    )
    margins = (
        (tp + fn, NO_POSITIVES),
        (tn + fp, NO_NEGATIVES),
        (tp + fp, _NONE_RETURNED),
        (tn + fn, _ALL_RETURNED),
    )
    empty = next((why for size, why in margins if size == 0), None)
    if empty is not None:
        return empty
    return ((tp * tn) - (fp * fn)) / math.sqrt(math.prod(s for s, _ in margins))


def compute_metrics(cm: ConfusionMatrix) -> ExperimentMetrics:
    """Every classification metric of a confusion matrix. A ratio whose
    denominator is empty is not measured, and says which controls it lacks; a
    ratio that counts false positives needs negative controls.

    :param cm: Confusion matrix.
    :returns: Full metrics object.
    """
    tp, fp, tn, fn = (
        cm.true_positives,
        cm.false_positives,
        cm.true_negatives,
        cm.false_negatives,
    )
    negatives = tn + fp
    positives = tp + fn
    sensitivity = _ratio(tp, positives, NO_POSITIVES)
    specificity = _ratio(tn, negatives, NO_NEGATIVES)
    precision = _ratio(tp, tp + fp, _NONE_RETURNED) if negatives > 0 else NO_NEGATIVES
    npv = (
        _ratio(tn, tn + fn, _ALL_RETURNED)
        if positives > 0 and negatives > 0
        else NO_POSITIVES
        if positives == 0
        else NO_NEGATIVES
    )
    return ExperimentMetrics(
        confusion_matrix=cm,
        sensitivity=sensitivity,
        specificity=specificity,
        precision=precision,
        negative_predictive_value=npv,
        false_positive_rate=_ratio(fp, negatives, NO_NEGATIVES),
        false_negative_rate=_ratio(fn, positives, NO_POSITIVES),
        f1_score=_both(precision, sensitivity, _f1),
        mcc=_mcc(cm),
        balanced_accuracy=_both(sensitivity, specificity, lambda a, b: (a + b) / 2),
        youdens_j=_both(sensitivity, specificity, lambda a, b: a + b - 1.0),
        total_positives=positives,
        total_negatives=negatives,
    )


def metric_text(value: float | Unread) -> str:
    """A metric to two places, or why it was not measured."""
    match value:
        case Unread(reason=reason):
            return f"not measured ({reason})"
        case _:
            return f"{value:.2f}"


def metrics_from_control_result(result: ControlTestResult) -> ExperimentMetrics:
    """Build metrics from the result returned by :func:`run_positive_negative_controls`.

    :param result: Typed control-test result.
    :returns: Full metrics.
    """
    pos = result.positive
    neg = result.negative

    pos_count = pos.intersection_count if pos else 0
    pos_total = pos.controls_count if pos else 0
    neg_count = neg.intersection_count if neg else 0
    neg_total = neg.controls_count if neg else 0

    cm = compute_confusion_matrix(
        positive_hits=pos_count,
        total_positives=pos_total,
        negative_hits=neg_count,
        total_negatives=neg_total,
    )
    return compute_metrics(cm)
