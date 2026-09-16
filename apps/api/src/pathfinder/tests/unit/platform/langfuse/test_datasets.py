"""Tests for Langfuse dataset management - graceful degradation only."""

from unittest.mock import patch

from pathfinder.platform.langfuse.datasets import (
    DatasetItemInput,
    run_evaluation_experiment,
    seed_dataset,
)


def test_seed_dataset_noop_when_langfuse_disabled() -> None:
    """No-op when get_langfuse() returns None."""
    with patch(
        "pathfinder.platform.langfuse.datasets.get_langfuse",
        return_value=None,
    ):
        seed_dataset("test-ds", [DatasetItemInput(input={"q": "hello"})])


def test_run_experiment_noop_when_disabled() -> None:
    """Returns None when Langfuse is disabled."""
    with patch(
        "pathfinder.platform.langfuse.datasets.get_langfuse",
        return_value=None,
    ):
        result = run_evaluation_experiment(
            dataset_name="ds",
            experiment_name="exp",
            task_fn=lambda item: None,
        )
    assert result is None
