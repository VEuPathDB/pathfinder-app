"""run_experiment orchestration with the WDK seams mocked.

It verifies the lifecycle (running -> completed/error) and that metrics are
computed for real from the control-test result. The control engine and gene
hydration are stubbed.
"""

from __future__ import annotations

import math
from typing import Any
from unittest.mock import AsyncMock

import pytest
from veupathdb_mcp.controls import (
    ControlTargetData,
    ControlTestResult,
    NegativeControls,
    PositiveControls,
)

from pathfinder.services.experiment import service
from pathfinder.services.experiment.service import run_experiment, shared
from pathfinder.services.experiment.service.phases import evaluate
from pathfinder.services.experiment.types.experiment import (
    Experiment,
    ExperimentConfig,
)


class _Store:
    """Records a copy of every experiment the run saves."""

    def __init__(self) -> None:
        self.saved: list[Experiment] = []

    def save(self, experiment: Experiment) -> None:
        self.saved.append(experiment.model_copy(deep=True))


def _config() -> ExperimentConfig:
    return ExperimentConfig(
        site_id="plasmodb",
        record_type="transcript",
        search_name="GenesByRNASeq",
        parameters={},
        positive_controls=[f"g{i}" for i in range(1, 11)],
        negative_controls=["g7", "g8", *[f"n{i}" for i in range(8)]],
        controls_search_name="GenesByGeneList",
        controls_param_name="ds_gene_ids",
    )


def _known_result() -> Any:
    # 8 of 10 positives hit, 2 of 10 negatives hit -> MCC 0.6.
    return ControlTestResult(
        target=ControlTargetData(estimated_size=8),
        positive=PositiveControls(
            recovered_ids=[f"g{i}" for i in range(1, 9)], missed_ids=["g9", "g10"]
        ),
        negative=NegativeControls(
            admitted_ids=["g7", "g8"], excluded_ids=[f"n{i}" for i in range(8)]
        ),
    )


def _mock_seams(monkeypatch: pytest.MonkeyPatch, *, controls: Any) -> _Store:
    store = _Store()
    monkeypatch.setattr(service, "get_experiment_store", lambda: store)
    monkeypatch.setattr(
        evaluate, "run_single_step_controls", AsyncMock(return_value=controls)
    )
    monkeypatch.setattr(
        shared, "extract_and_hydrate_genes", AsyncMock(return_value=([], [], [], []))
    )
    return store


@pytest.mark.asyncio
async def test_run_experiment_completes_with_real_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _mock_seams(monkeypatch, controls=_known_result())

    exp = await run_experiment(_config(), user_id="u1")

    assert exp.status == "completed"
    assert exp.metrics is not None
    assert math.isclose(exp.metrics.mcc, 0.6)
    assert math.isclose(exp.metrics.sensitivity, 0.8)
    assert [saved.status for saved in (store.saved[0], store.saved[-1])] == [
        "running",
        "completed",
    ]


@pytest.mark.asyncio
async def test_run_experiment_error_sets_status_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _mock_seams(monkeypatch, controls=_known_result())
    monkeypatch.setattr(
        evaluate,
        "run_single_step_controls",
        AsyncMock(side_effect=RuntimeError("WDK down")),
    )

    with pytest.raises(RuntimeError, match="WDK down"):
        await run_experiment(_config(), user_id="u1")

    assert store.saved[-1].status == "error"
    assert store.saved[-1].error is not None


def test_the_experiment_model_carries_no_lab_result() -> None:
    removed = {
        "rank_metrics",
        "step_analysis",
        "tree_optimization",
        "optimization_result",
        "cross_validation",
        "robustness",
        "batch_id",
        "benchmark_id",
        "control_set_label",
        "is_primary_benchmark",
        "gene_set_membership",
        "notes",
        "enrichment_results",
        "wdk_strategy_id",
        "wdk_step_id",
    }
    assert set(Experiment.model_fields) & removed == set()


def test_the_config_model_carries_no_lab_knobs() -> None:
    removed = {
        "optimization_specs",
        "optimization_budget",
        "optimization_objective",
        "optimization_target_step",
        "threshold_knobs",
        "operator_knobs",
        "tree_optimization_objective",
        "tree_optimization_budget",
        "enable_step_analysis",
        "step_analysis_phases",
        "sort_attribute",
        "sort_direction",
        "enable_cross_validation",
        "k_folds",
        "mode",
        "step_tree",
        "source_strategy_id",
        "gene_set_id",
        "control_set_id",
        "parent_experiment_id",
        "max_list_size",
        "enrichment_types",
        "target_gene_ids",
    }
    assert set(ExperimentConfig.model_fields) & removed == set()
