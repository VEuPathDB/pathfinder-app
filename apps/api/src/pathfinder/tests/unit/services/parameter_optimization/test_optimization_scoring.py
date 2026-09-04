from __future__ import annotations

import pytest

from pathfinder.services.parameter_optimization.config import OptimizationConfig
from pathfinder.services.parameter_optimization.scoring import (
    _compute_score,
    _score_mcc,
)


class TestScoreMcc:
    def test_balanced_case_matches_closed_form(self) -> None:
        assert _score_mcc(0.8, 0.9, 0.1) == pytest.approx(0.7035264706814485)

    def test_perfect_classifier_is_one(self) -> None:
        assert _score_mcc(1.0, 1.0, 0.0) == pytest.approx(1.0)

    def test_zero_denominator_guard_returns_zero(self) -> None:
        assert _score_mcc(0.0, 1.0, 0.0) == 0.0


class TestComputeScoreByObjective:
    def test_f1_uses_precision_from_intersection_hits(self) -> None:
        cfg = OptimizationConfig(objective="f1")
        score = _compute_score(0.6, 0.1, cfg, positive_hits=30, negative_hits=10)
        assert score == pytest.approx(0.6666666666666665)

    def test_f_beta_weights_recall_with_beta(self) -> None:
        cfg = OptimizationConfig(objective="f_beta", beta=2.0)
        score = _compute_score(0.6, 0.1, cfg, positive_hits=30, negative_hits=10)
        assert score == pytest.approx(0.625)

    def test_balanced_accuracy_is_mean_of_recall_and_specificity(self) -> None:
        cfg = OptimizationConfig(objective="balanced_accuracy")
        assert _compute_score(0.6, 0.1, cfg) == pytest.approx(0.75)

    def test_youdens_j_is_recall_plus_specificity_minus_one(self) -> None:
        cfg = OptimizationConfig(objective="youdens_j")
        assert _compute_score(0.6, 0.1, cfg) == pytest.approx(0.5)

    def test_custom_blends_recall_against_raw_fpr(self) -> None:
        cfg = OptimizationConfig(
            objective="custom", recall_weight=1.0, precision_weight=1.0
        )
        assert _compute_score(0.6, 0.1, cfg) == pytest.approx(0.5)

    def test_precision_falls_back_to_specificity_without_hits(self) -> None:
        cfg = OptimizationConfig(objective="precision")
        assert _compute_score(0.6, 0.1, cfg) == pytest.approx(0.9)

    def test_none_recall_and_fpr_score_zero_for_f1(self) -> None:
        cfg = OptimizationConfig(objective="f1")
        assert _compute_score(None, None, cfg) == 0.0


class TestEstimatedSizePenalty:
    def test_penalty_subtracts_size_fraction_of_default_genome(self) -> None:
        cfg = OptimizationConfig(objective="f1", estimated_size_penalty=0.1)
        score = _compute_score(
            0.6, 0.1, cfg, estimated_size=5000, positive_hits=30, negative_hits=10
        )
        assert score == pytest.approx(0.6416666666666665)

    def test_penalty_clamps_at_zero(self) -> None:
        cfg = OptimizationConfig(objective="recall", estimated_size_penalty=5.0)
        assert _compute_score(0.05, 0.5, cfg, estimated_size=20_000) == 0.0

    def test_no_penalty_when_weight_zero(self) -> None:
        cfg = OptimizationConfig(objective="recall", estimated_size_penalty=0.0)
        assert _compute_score(0.6, 0.1, cfg, estimated_size=999_999) == pytest.approx(
            0.6
        )
