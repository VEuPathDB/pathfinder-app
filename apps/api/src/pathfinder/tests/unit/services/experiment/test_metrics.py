"""Correctness tests for the classification-metrics engine - hand-computed
expected values, not just shape checks. A confusion matrix of tp=8, fn=2,
fp=2, tn=10-2=8 gives the round numbers used throughout.
"""

from __future__ import annotations

import math

from pathfinder.services.experiment.metrics import (
    compute_confusion_matrix,
    compute_metrics,
    evaluate_gene_ids_against_controls,
    metrics_from_control_result,
)


def test_confusion_matrix_from_hits() -> None:
    cm = compute_confusion_matrix(
        positive_hits=8, total_positives=10, negative_hits=2, total_negatives=10
    )
    assert (cm.true_positives, cm.false_negatives) == (8, 2)
    assert (cm.false_positives, cm.true_negatives) == (2, 8)


def test_confusion_matrix_clamps_impossible_negatives() -> None:
    # hits can't exceed totals; clamp rather than emit a negative cell.
    cm = compute_confusion_matrix(
        positive_hits=12, total_positives=10, negative_hits=0, total_negatives=5
    )
    assert cm.false_negatives == 0  # 10 - 12 clamped to 0
    assert cm.true_negatives == 5


def test_metrics_hand_computed() -> None:
    cm = compute_confusion_matrix(
        positive_hits=8, total_positives=10, negative_hits=2, total_negatives=10
    )
    m = compute_metrics(cm, total_results=100)
    assert math.isclose(m.sensitivity, 0.8)
    assert math.isclose(m.specificity, 0.8)
    assert math.isclose(m.precision, 0.8)
    assert math.isclose(m.negative_predictive_value, 0.8)
    assert math.isclose(m.false_positive_rate, 0.2)
    assert math.isclose(m.false_negative_rate, 0.2)
    assert math.isclose(m.f1_score, 0.8)
    assert math.isclose(m.mcc, 0.6)  # (64-4)/sqrt(10*10*10*10) = 60/100
    assert math.isclose(m.balanced_accuracy, 0.8)
    assert math.isclose(m.youdens_j, 0.6)
    assert m.total_results == 100
    assert m.total_positives == 10
    assert m.total_negatives == 10


def test_metrics_zero_denominators_are_safe() -> None:
    cm = compute_confusion_matrix(
        positive_hits=0, total_positives=0, negative_hits=0, total_negatives=0
    )
    m = compute_metrics(cm)
    assert m.sensitivity == 0.0
    assert m.precision == 0.0
    assert m.mcc == 0.0
    assert m.f1_score == 0.0


def test_perfect_classifier_mcc_is_one() -> None:
    cm = compute_confusion_matrix(
        positive_hits=10, total_positives=10, negative_hits=0, total_negatives=10
    )
    m = compute_metrics(cm)
    assert math.isclose(m.mcc, 1.0)
    assert math.isclose(m.f1_score, 1.0)


def test_anti_correlated_classifier_has_negative_mcc() -> None:
    # A worse-than-random classifier must produce a NEGATIVE MCC so callers can
    # tell "actively misleading" from merely "uninformative" (mcc == 0).
    # TP=2, FN=8, FP=8, TN=2:
    #   mcc = (2*2 - 8*8) / sqrt(10*10*10*10) = (4 - 64)/100 = -0.6
    cm = compute_confusion_matrix(
        positive_hits=2, total_positives=10, negative_hits=8, total_negatives=10
    )
    m = compute_metrics(cm)
    assert math.isclose(m.mcc, -0.6)
    # Symmetric: flipping to the well-classified counts gives +0.6.
    cm2 = compute_confusion_matrix(
        positive_hits=8, total_positives=10, negative_hits=2, total_negatives=10
    )
    assert math.isclose(compute_metrics(cm2).mcc, 0.6)


def test_mcc_is_zero_not_nan_when_one_class_absent() -> None:
    # TP=5, FP=5, TN=FN=0. mcc denominator factor (tn+fp)*(tn+fn) collapses to
    # (0+5)*(0+0) = 0, so the whole sqrt is 0. MCC must be defined as 0.0, never
    # NaN/inf - a NaN would silently poison downstream means/CIs.
    cm = compute_confusion_matrix(
        positive_hits=5, total_positives=5, negative_hits=5, total_negatives=5
    )
    m = compute_metrics(cm)
    assert m.mcc == 0.0
    assert not math.isnan(m.mcc)
    assert not math.isinf(m.mcc)


def test_evaluate_gene_ids_against_controls_pure_set_ops() -> None:
    result = evaluate_gene_ids_against_controls(
        gene_ids=["g1", "g2", "g3", "g4"],
        positive_controls=["g1", "g2", "missing"],
        negative_controls=["g3", "negmiss"],
    )
    assert result.positive is not None
    assert result.positive.controls_count == 3
    assert result.positive.intersection_count == 2  # g1, g2
    assert math.isclose(result.positive.recall or 0.0, 2 / 3)
    assert result.negative is not None
    assert result.negative.intersection_count == 1  # g3
    assert math.isclose(result.negative.false_positive_rate or 0.0, 1 / 2)


def test_metrics_from_control_result_end_to_end() -> None:
    result = evaluate_gene_ids_against_controls(
        gene_ids=["g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8"],
        positive_controls=[f"g{i}" for i in range(1, 11)],  # g1..g10, 8 hit
        negative_controls=["g7", "g8"] + [f"n{i}" for i in range(8)],  # 2 hit of 10
    )
    m = metrics_from_control_result(result)
    assert m.confusion_matrix.true_positives == 8
    assert m.confusion_matrix.false_negatives == 2
    assert m.confusion_matrix.false_positives == 2
    assert math.isclose(m.sensitivity, 0.8)
    assert math.isclose(m.mcc, 0.6)
