"""Correctness tests for the classification-metrics engine - hand-computed
expected values, not just shape checks. A confusion matrix of tp=8, fn=2,
fp=2, tn=10-2=8 gives the round numbers used throughout.
"""

from __future__ import annotations

import pytest
from veupathdb_mcp.controls import (
    ControlTargetData,
    ControlTestResult,
    NegativeControls,
    PositiveControls,
)

from strategist.domain.unread import Unread
from strategist.services.experiment.metrics import (
    compute_confusion_matrix,
    compute_metrics,
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
    m = compute_metrics(cm)
    assert m.sensitivity == pytest.approx(0.8)
    assert m.specificity == pytest.approx(0.8)
    assert m.precision == pytest.approx(0.8)
    assert m.negative_predictive_value == pytest.approx(0.8)
    assert m.false_positive_rate == pytest.approx(0.2)
    assert m.false_negative_rate == pytest.approx(0.2)
    assert m.f1_score == pytest.approx(0.8)
    assert m.mcc == pytest.approx(0.6)  # (64-4)/sqrt(10*10*10*10) = 60/100
    assert m.balanced_accuracy == pytest.approx(0.8)
    assert m.youdens_j == pytest.approx(0.6)
    assert m.total_positives == 10
    assert m.total_negatives == 10


def test_no_controls_measure_nothing() -> None:
    cm = compute_confusion_matrix(
        positive_hits=0, total_positives=0, negative_hits=0, total_negatives=0
    )
    m = compute_metrics(cm)
    assert (m.sensitivity, m.precision, m.mcc, m.f1_score) == (
        Unread(reason="no positive controls"),
        Unread(reason="no negative controls"),
        Unread(reason="no positive controls"),
        Unread(reason="no negative controls"),
    )


def test_perfect_classifier_mcc_is_one() -> None:
    cm = compute_confusion_matrix(
        positive_hits=10, total_positives=10, negative_hits=0, total_negatives=10
    )
    m = compute_metrics(cm)
    assert m.mcc == pytest.approx(1.0)
    assert m.f1_score == pytest.approx(1.0)


def test_anti_correlated_classifier_has_negative_mcc() -> None:
    # A worse-than-random classifier must produce a NEGATIVE MCC so callers can
    # tell "actively misleading" from merely "uninformative" (mcc == 0).
    # TP=2, FN=8, FP=8, TN=2:
    #   mcc = (2*2 - 8*8) / sqrt(10*10*10*10) = (4 - 64)/100 = -0.6
    cm = compute_confusion_matrix(
        positive_hits=2, total_positives=10, negative_hits=8, total_negatives=10
    )
    m = compute_metrics(cm)
    assert m.mcc == pytest.approx(-0.6)
    # Symmetric: flipping to the well-classified counts gives +0.6.
    cm2 = compute_confusion_matrix(
        positive_hits=8, total_positives=10, negative_hits=2, total_negatives=10
    )
    assert compute_metrics(cm2).mcc == pytest.approx(0.6)


def test_metrics_from_control_result_end_to_end() -> None:
    result = ControlTestResult(
        target=ControlTargetData(estimated_size=8),
        positive=PositiveControls(
            recovered_ids=[f"g{i}" for i in range(1, 9)], missed_ids=["g9", "g10"]
        ),
        negative=NegativeControls(
            admitted_ids=["g7", "g8"], excluded_ids=[f"n{i}" for i in range(8)]
        ),
    )
    m = metrics_from_control_result(result)
    assert m.confusion_matrix.true_positives == 8
    assert m.confusion_matrix.false_negatives == 2
    assert m.confusion_matrix.false_positives == 2
    assert m.sensitivity == pytest.approx(0.8)
    assert m.mcc == pytest.approx(0.6)
