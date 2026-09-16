"""A batch run derives one config per organism and carries everything else."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_core import PydanticUndefined
from veupathdb.domain.parameters import SinglePickValue
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.services.experiment import streaming
from pathfinder.services.experiment.store import _row_from_experiment
from pathfinder.services.experiment.streaming import (
    organism_config,
    organism_varies_nothing,
    stream_batch_experiment,
)
from pathfinder.services.experiment.types import (
    BatchExperimentConfig,
    BatchOrganismTarget,
    Experiment,
    ExperimentConfig,
)

SET_ID = "gs-gametocyte-secreted"
USER_ID = "ba5eba11-0000-4000-8000-00000000cafe"
ORGANISM = "Plasmodium falciparum 3D7"
SECOND_ORGANISM = "Plasmodium vivax P01"
BASE_ORGANISM = "Plasmodium berghei ANKA"
ORGANISM_PARAM = "organism"
BASE_NAME = "gametocyte secreted"
# The values one organism's run sets for itself. Every other field is carried.
PER_ORGANISM_FIELDS = frozenset(
    {"parameters", "positive_controls", "negative_controls", "name"},
)


def _base_config() -> ExperimentConfig:
    """A base holding no field at its default, so a dropped field shows up."""
    return ExperimentConfig(
        site_id="plasmodb",
        record_type="transcript",
        search_name="GenesByRNASeq",
        parameters={ORGANISM_PARAM: SinglePickValue(value=BASE_ORGANISM)},
        positive_controls=["PF3D7_0304600"],
        negative_controls=["PF3D7_0930300"],
        controls_search_name="GeneByLocusTag",
        controls_param_name="ds_gene_ids",
        controls_value_format="comma",
        enable_cross_validation=True,
        k_folds=7,
        enrichment_types=["go_function"],
        name=BASE_NAME,
        description="the evaluation the set started",
        parameter_display_values={ORGANISM_PARAM: "P. berghei ANKA"},
        mode="multi-step",
        step_tree=StrategyStepNode(
            id="root",
            search_name="GenesByTaxon",
            display_name="Taxon",
            parameters={ORGANISM_PARAM: SinglePickValue(value=BASE_ORGANISM)},
        ),
        source_strategy_id="strat-7",
        control_set_id="cs-1",
        gene_set_id=SET_ID,
        max_list_size=250,
        parent_experiment_id="exp-parent",
        target_gene_ids=["PF3D7_0304600"],
    )


def test_the_base_under_test_leaves_no_field_at_its_default() -> None:
    """A field left at its default would look carried even when it is dropped.

    A field added to the config fails here until the base above names it.
    """
    base = _base_config()

    at_default = [
        name
        for name, field in ExperimentConfig.model_fields.items()
        if field.get_default(call_default_factory=True) is not PydanticUndefined
        and getattr(base, name) == field.get_default(call_default_factory=True)
    ]

    assert at_default == []


def test_the_organism_config_changes_only_the_per_organism_fields() -> None:
    base = _base_config()
    target = BatchOrganismTarget(
        organism=ORGANISM,
        positive_controls=["PVP01_0102300"],
        negative_controls=["PVP01_0403000"],
    )

    derived = organism_config(base, ORGANISM_PARAM, target)

    changed = {
        name
        for name in ExperimentConfig.model_fields
        if getattr(derived, name) != getattr(base, name)
    }
    assert changed == PER_ORGANISM_FIELDS


def test_the_organism_config_keeps_the_gene_set_the_batch_names() -> None:
    derived = organism_config(
        _base_config(),
        ORGANISM_PARAM,
        BatchOrganismTarget(organism=ORGANISM),
    )

    assert derived.gene_set_id == SET_ID


def test_the_organism_config_pins_the_organism_and_names_it() -> None:
    base = _base_config()

    derived = organism_config(
        base,
        ORGANISM_PARAM,
        BatchOrganismTarget(organism=ORGANISM),
    )

    assert derived.parameters[ORGANISM_PARAM] == SinglePickValue(value=ORGANISM)
    assert derived.name == f"{BASE_NAME} ({ORGANISM})"
    assert base.parameters[ORGANISM_PARAM] == SinglePickValue(value=BASE_ORGANISM)


def test_a_target_that_names_no_controls_keeps_the_base_controls() -> None:
    derived = organism_config(
        _base_config(),
        ORGANISM_PARAM,
        BatchOrganismTarget(organism=ORGANISM),
    )

    assert derived.positive_controls == ["PF3D7_0304600"]
    assert derived.negative_controls == ["PF3D7_0930300"]


def test_a_target_that_names_controls_overrides_the_base_controls() -> None:
    derived = organism_config(
        _base_config(),
        ORGANISM_PARAM,
        BatchOrganismTarget(
            organism=ORGANISM,
            positive_controls=["PVP01_0102300"],
            negative_controls=[],
        ),
    )

    assert derived.positive_controls == ["PVP01_0102300"]
    assert derived.negative_controls == []


def _runnable_base() -> ExperimentConfig:
    """A base the organism parameter can vary: one search, no fixed gene list."""
    return _base_config().model_copy(
        update={"mode": "single", "step_tree": None, "target_gene_ids": None},
    )


def _record_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> list[ExperimentConfig]:
    ran: list[ExperimentConfig] = []

    async def _run_experiment(config: ExperimentConfig, **kwargs: Any) -> Experiment:
        del kwargs
        ran.append(config)
        return Experiment(
            id=f"exp-{len(ran)}",
            config=config,
            user_id=USER_ID,
            status="completed",
        )

    monkeypatch.setattr(streaming, "run_experiment", _run_experiment)
    return ran


async def test_a_batch_over_a_step_tree_is_refused_before_any_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A step tree holds its own organism, so the override would change nothing."""
    ran = _record_runs(monkeypatch)
    batch = BatchExperimentConfig(
        base_config=_base_config().model_copy(update={"target_gene_ids": None}),
        organism_param_name=ORGANISM_PARAM,
        target_organisms=[BatchOrganismTarget(organism=ORGANISM)],
    )

    events = [event async for event in stream_batch_experiment(batch, user_id=USER_ID)]

    final = events[-1]
    assert final.type == "batch_error", final
    assert "step tree" in final.error
    assert ran == []


async def test_a_batch_over_a_fixed_gene_list_is_refused_before_any_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fixed gene list is evaluated without a search, so no organism varies it."""
    ran = _record_runs(monkeypatch)
    batch = BatchExperimentConfig(
        base_config=_base_config(),
        organism_param_name=ORGANISM_PARAM,
        target_organisms=[BatchOrganismTarget(organism=ORGANISM)],
    )

    events = [event async for event in stream_batch_experiment(batch, user_id=USER_ID)]

    final = events[-1]
    assert final.type == "batch_error", final
    assert "gene list" in final.error
    assert ran == []


async def test_a_batch_over_a_base_that_names_no_search_is_refused_before_any_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty search name runs no search, so no organism parameter varies one."""
    ran = _record_runs(monkeypatch)
    batch = BatchExperimentConfig(
        base_config=_runnable_base().model_copy(update={"search_name": ""}),
        organism_param_name=ORGANISM_PARAM,
        target_organisms=[BatchOrganismTarget(organism=ORGANISM)],
    )

    events = [event async for event in stream_batch_experiment(batch, user_id=USER_ID)]

    final = events[-1]
    assert final.type == "batch_error", final
    assert final.error == (
        "This batch cannot vary by organism: the base names no search, so it "
        "has no organism parameter to set."
    )
    assert ran == []


def test_the_guard_names_one_reason_per_base_it_refuses() -> None:
    """A single search with parameters is exactly what an organism can vary."""
    runnable = _runnable_base()

    reasons = [
        organism_varies_nothing(runnable),
        organism_varies_nothing(runnable.model_copy(update={"search_name": ""})),
        organism_varies_nothing(
            runnable.model_copy(update={"target_gene_ids": ["PF3D7_0304600"]}),
        ),
    ]

    assert reasons == [
        None,
        "the base names no search, so it has no organism parameter to set",
        "the base evaluates a fixed gene list, which runs no search",
    ]


def _record_runs_with_one_failure(
    monkeypatch: pytest.MonkeyPatch,
    failing_organism: str,
) -> list[str]:
    """Stand in for a run that raises for one organism, and name every run."""
    given_ids: list[str] = []

    async def _run_experiment(
        config: ExperimentConfig,
        *,
        experiment_id: str,
        **kwargs: Any,
    ) -> Experiment:
        del kwargs
        given_ids.append(experiment_id)
        if _organism_of(config) == failing_organism:
            msg = "WDK answered 500 for the organism"
            raise RuntimeError(msg)
        return Experiment(
            id=experiment_id,
            config=config,
            user_id=USER_ID,
            status="completed",
        )

    monkeypatch.setattr(streaming, "run_experiment", _run_experiment)
    return given_ids


def _organism_of(config: ExperimentConfig) -> str:
    """The organism one derived config is pinned to."""
    return SinglePickValue.model_validate(config.parameters[ORGANISM_PARAM]).value


async def test_an_organism_that_fails_is_reported_beside_the_ones_that_ran(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A batch reports one result per organism, whether it ran or failed."""
    given_ids = _record_runs_with_one_failure(monkeypatch, BASE_ORGANISM)
    batch = BatchExperimentConfig(
        base_config=_runnable_base(),
        organism_param_name=ORGANISM_PARAM,
        target_organisms=[
            BatchOrganismTarget(organism=ORGANISM),
            BatchOrganismTarget(organism=BASE_ORGANISM),
            BatchOrganismTarget(organism=SECOND_ORGANISM),
        ],
    )

    events = [event async for event in stream_batch_experiment(batch, user_id=USER_ID)]

    final = events[-1]
    assert final.type == "batch_complete", final
    experiments = [Experiment.model_validate(raw) for raw in final.experiments]
    assert [_organism_of(exp.config) for exp in experiments] == [
        ORGANISM,
        BASE_ORGANISM,
        SECOND_ORGANISM,
    ]
    assert [exp.status for exp in experiments] == ["completed", "error", "completed"]
    assert [exp.id for exp in experiments] == given_ids
    assert experiments[1].error == "An internal error occurred"
    assert experiments[1].user_id == USER_ID
    assert {exp.batch_id for exp in experiments} == {final.batch_id}
    assert experiments[1].config.gene_set_id == SET_ID


async def test_a_batch_run_from_a_gene_set_stores_every_experiment_with_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every organism's experiment is findable from the set the batch started from."""
    ran = _record_runs(monkeypatch)
    batch = BatchExperimentConfig(
        base_config=_runnable_base(),
        organism_param_name=ORGANISM_PARAM,
        target_organisms=[
            BatchOrganismTarget(organism=ORGANISM),
            BatchOrganismTarget(organism=SECOND_ORGANISM),
        ],
    )

    events = [event async for event in stream_batch_experiment(batch, user_id=USER_ID)]

    final = events[-1]
    assert final.type == "batch_complete", final
    experiments = [Experiment.model_validate(raw) for raw in final.experiments]
    assert [exp.id for exp in experiments] == ["exp-1", "exp-2"]
    assert [exp.config.gene_set_id for exp in experiments] == [SET_ID, SET_ID]
    assert [_row_from_experiment(exp)["gene_set_id"] for exp in experiments] == [
        SET_ID,
        SET_ID,
    ]
    assert [exp.config.name for exp in experiments] == [
        f"{BASE_NAME} ({ORGANISM})",
        f"{BASE_NAME} ({SECOND_ORGANISM})",
    ]
    assert [cfg.parameters[ORGANISM_PARAM] for cfg in ran] == [
        SinglePickValue(value=ORGANISM),
        SinglePickValue(value=SECOND_ORGANISM),
    ]
