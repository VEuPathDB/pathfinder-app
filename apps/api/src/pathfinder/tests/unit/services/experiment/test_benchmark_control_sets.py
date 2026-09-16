"""A benchmark runs one experiment per control set and reports every one."""

from __future__ import annotations

from typing import Any

import pytest

from pathfinder.services.experiment import streaming
from pathfinder.services.experiment.streaming import stream_benchmark
from pathfinder.services.experiment.types import Experiment, ExperimentConfig

USER_ID = "ba5eba11-0000-4000-8000-00000000cafe"
SET_ID = "gs-gametocyte-secreted"
GAMETOCYTE = "gametocyte surface"
MEROZOITE = "merozoite invasion"
BASE_NAME = "gametocyte secreted"
# The shape stream_benchmark takes: label, positives, negatives, id, primary.
CONTROL_SETS: list[tuple[str, list[str], list[str], str | None, bool]] = [
    (GAMETOCYTE, ["PF3D7_0304600"], ["PF3D7_0930300"], "cs-gam", True),
    (MEROZOITE, ["PF3D7_1133400"], ["PF3D7_0304600"], "cs-mero", False),
]


def _base_config() -> ExperimentConfig:
    return ExperimentConfig(
        site_id="plasmodb",
        record_type="transcript",
        search_name="GenesByRNASeq",
        parameters={},
        positive_controls=[],
        negative_controls=[],
        controls_search_name="GeneByLocusTag",
        controls_param_name="ds_gene_ids",
        name=BASE_NAME,
        gene_set_id=SET_ID,
    )


def _record_runs_with_one_failure(
    monkeypatch: pytest.MonkeyPatch,
    failing_label: str,
) -> list[str]:
    """Stand in for a run that raises for one control set, and name every run."""
    given_ids: list[str] = []

    async def _run_experiment(
        config: ExperimentConfig,
        *,
        experiment_id: str,
        **kwargs: Any,
    ) -> Experiment:
        del kwargs
        given_ids.append(experiment_id)
        if config.name.endswith(f"[{failing_label}]"):
            msg = "WDK answered 500 for the control set"
            raise RuntimeError(msg)
        return Experiment(
            id=experiment_id,
            config=config,
            user_id=USER_ID,
            status="completed",
        )

    monkeypatch.setattr(streaming, "run_experiment", _run_experiment)
    return given_ids


async def test_a_control_set_that_fails_is_reported_beside_the_ones_that_ran(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A benchmark reports one result per control set, whether it ran or failed."""
    given_ids = _record_runs_with_one_failure(monkeypatch, MEROZOITE)

    events = [
        event
        async for event in stream_benchmark(
            _base_config(),
            CONTROL_SETS,
            user_id=USER_ID,
        )
    ]

    final = events[-1]
    assert final.type == "benchmark_complete", final
    experiments = [Experiment.model_validate(raw) for raw in final.experiments]
    assert [exp.control_set_label for exp in experiments] == [GAMETOCYTE, MEROZOITE]
    assert [exp.status for exp in experiments] == ["completed", "error"]
    assert [exp.is_primary_benchmark for exp in experiments] == [True, False]
    assert sorted(exp.id for exp in experiments) == sorted(given_ids)
    assert experiments[1].error == "An internal error occurred"
    assert experiments[1].user_id == USER_ID
    assert experiments[1].config.control_set_id == "cs-mero"
    assert {exp.benchmark_id for exp in experiments} == {final.benchmark_id}


async def test_every_control_set_names_its_own_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each run carries the control set's own label, ids and controls."""
    _record_runs_with_one_failure(monkeypatch, "no such label")

    events = [
        event
        async for event in stream_benchmark(
            _base_config(),
            CONTROL_SETS,
            user_id=USER_ID,
        )
    ]

    final = events[-1]
    assert final.type == "benchmark_complete", final
    experiments = [Experiment.model_validate(raw) for raw in final.experiments]
    assert [exp.config.name for exp in experiments] == [
        f"{BASE_NAME} [{GAMETOCYTE}]",
        f"{BASE_NAME} [{MEROZOITE}]",
    ]
    assert [exp.config.positive_controls for exp in experiments] == [
        ["PF3D7_0304600"],
        ["PF3D7_1133400"],
    ]
    assert [exp.config.gene_set_id for exp in experiments] == [SET_ID, SET_ID]
