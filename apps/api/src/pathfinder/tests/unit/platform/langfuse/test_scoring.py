"""Tests for Langfuse score emission - graceful degradation and resilience."""

from unittest.mock import MagicMock, patch

from pathfinder.platform.langfuse.scoring import emit_evaluation_scores
from pathfinder.services.experiment.types import ConfusionMatrix, ExperimentMetrics

_NETWORK_ERROR = OSError("Network blip")


def _make_metrics() -> ExperimentMetrics:
    return ExperimentMetrics(
        confusion_matrix=ConfusionMatrix(
            true_positives=10,
            false_positives=2,
            true_negatives=8,
            false_negatives=1,
        ),
        sensitivity=0.9,
        specificity=0.8,
        precision=0.83,
        negative_predictive_value=0.89,
        false_positive_rate=0.2,
        false_negative_rate=0.1,
        f1_score=0.87,
        mcc=0.7,
        balanced_accuracy=0.85,
        youdens_j=0.7,
    )


def test_emit_scores_noop_when_langfuse_disabled() -> None:
    """No-op when get_langfuse() returns None."""
    with patch(
        "pathfinder.platform.langfuse.scoring.get_langfuse",
        return_value=None,
    ):
        emit_evaluation_scores("trace-123", _make_metrics())  # Should not raise


def test_emit_scores_continues_on_individual_failure() -> None:
    """A failure on one score does not prevent the others from being sent."""
    mock_client = MagicMock()
    call_count = 0

    def side_effect(**kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise _NETWORK_ERROR

    mock_client.create_score.side_effect = side_effect
    with patch(
        "pathfinder.platform.langfuse.scoring.get_langfuse",
        return_value=mock_client,
    ):
        emit_evaluation_scores("trace-err", _make_metrics())

    # All 7 attempted even though one raised
    assert mock_client.create_score.call_count == 7
