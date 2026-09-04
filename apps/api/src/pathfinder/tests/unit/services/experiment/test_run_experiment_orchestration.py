"""run_experiment orchestration with the WDK seams mocked — verifies the
lifecycle (running -> completed/error), the five phases it runs, that metrics
are computed for real from the control-test result, progress events are
emitted, and failures are surfaced. No live WDK: the control engine, strategy
materialization and gene enrichment are all stubbed.
"""

from __future__ import annotations

import math
from typing import Any
from unittest.mock import AsyncMock

import pytest

from pathfinder.services.experiment import service as service_module
from pathfinder.services.experiment.metrics import (
    evaluate_gene_ids_against_controls,
)
from pathfinder.services.experiment.service import run_experiment, shared
from pathfinder.services.experiment.service.phases import evaluate as evaluate_phase
from pathfinder.services.experiment.service.phases import validate as validate_phase
from pathfinder.services.experiment.types.experiment import (
    Experiment,
    ExperimentConfig,
)


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
    return evaluate_gene_ids_against_controls(
        gene_ids=[f"g{i}" for i in range(1, 9)],
        positive_controls=[f"g{i}" for i in range(1, 11)],
        negative_controls=["g7", "g8", *[f"n{i}" for i in range(8)]],
    )


def _mock_seams(monkeypatch: pytest.MonkeyPatch, *, controls: Any) -> None:
    monkeypatch.setattr(
        evaluate_phase, "run_single_step_controls", AsyncMock(return_value=controls)
    )
    monkeypatch.setattr(
        evaluate_phase, "_persist_experiment_strategy", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        shared, "extract_and_hydrate_genes", AsyncMock(return_value=([], [], [], []))
    )
    monkeypatch.setattr(
        validate_phase, "phase_robustness", AsyncMock(return_value=None)
    )


@pytest.mark.asyncio
async def test_run_experiment_completes_with_real_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_seams(monkeypatch, controls=_known_result())
    events: list[dict[str, Any]] = []

    async def _cb(event: dict[str, Any]) -> None:
        events.append(event)

    exp = await run_experiment(_config(), user_id="u1", progress_callback=_cb)

    assert exp.status == "completed"
    assert exp.metrics is not None
    assert math.isclose(exp.metrics.mcc, 0.6)
    assert math.isclose(exp.metrics.sensitivity, 0.8)
    phases = [e["data"]["phase"] for e in events if e["type"] == "experiment_progress"]
    assert "started" in phases
    assert "completed" in phases


@pytest.mark.asyncio
async def test_run_experiment_error_sets_status_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_seams(monkeypatch, controls=_known_result())
    monkeypatch.setattr(
        evaluate_phase,
        "run_single_step_controls",
        AsyncMock(side_effect=RuntimeError("WDK down")),
    )
    events: list[dict[str, Any]] = []

    async def _cb(event: dict[str, Any]) -> None:
        events.append(event)

    with pytest.raises(RuntimeError, match="WDK down"):
        await run_experiment(_config(), user_id="u1", progress_callback=_cb)

    error_events = [
        e
        for e in events
        if e["type"] == "experiment_progress" and e["data"]["phase"] == "error"
    ]
    assert len(error_events) == 1


@pytest.mark.asyncio
async def test_run_experiment_calls_the_five_phases_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_seams(monkeypatch, controls=_known_result())
    called: list[str] = []

    def _spy(name: str) -> None:
        async def _record(*_args: Any, **_kwargs: Any) -> None:
            called.append(name)

        monkeypatch.setattr(service_module, name, _record)

    for name in (
        "phase_evaluate",
        "phase_persist_strategy",
        "phase_robustness",
        "phase_cross_validate",
        "phase_enrich",
    ):
        _spy(name)

    config = _config()
    config.enable_cross_validation = True
    config.enrichment_types = ["GO"]

    await run_experiment(config, user_id="u1")

    assert called == [
        "phase_evaluate",
        "phase_persist_strategy",
        "phase_robustness",
        "phase_cross_validate",
        "phase_enrich",
    ]


def test_the_experiment_model_carries_no_rank_or_optimization_result() -> None:
    removed = {
        "rank_metrics",
        "step_analysis",
        "tree_optimization",
        "optimization_result",
    }
    assert set(Experiment.model_fields) & removed == set()


def test_the_config_model_carries_no_optimization_or_sort_knobs() -> None:
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
    }
    assert set(ExperimentConfig.model_fields) & removed == set()
