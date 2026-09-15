"""An experiment carries the gene set the evaluation ran against."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.services.experiment.store import (
    _row_from_experiment,
    experiments_for_gene_set,
)
from pathfinder.services.experiment.types import Experiment, ExperimentConfig

USER_ID = uuid4()
OTHER_USER_ID = uuid4()
SET_ID = "gs-gametocyte-secreted"
OTHER_SET_ID = "gs-merozoite-surface"


def _config(gene_set_id: str | None) -> ExperimentConfig:
    return ExperimentConfig(
        site_id="plasmodb",
        record_type="gene",
        search_name="GenesByTaxon",
        parameters={},
        positive_controls=["PF3D7_0304600"],
        negative_controls=["PF3D7_0930300"],
        controls_search_name="GeneByLocusTag",
        controls_param_name="ds_gene_ids",
        name="gametocyte secreted (evaluation)",
        gene_set_id=gene_set_id,
    )


def _experiment(
    experiment_id: str,
    *,
    gene_set_id: str | None,
    created_at: str,
    user_id: str = str(USER_ID),
    batch_id: str | None = None,
    benchmark_id: str | None = None,
) -> Experiment:
    return Experiment(
        id=experiment_id,
        config=_config(gene_set_id),
        user_id=user_id,
        status="completed",
        created_at=created_at,
        batch_id=batch_id,
        benchmark_id=benchmark_id,
    )


def test_an_evaluation_started_from_a_set_records_the_set_id() -> None:
    exp = _experiment("exp-1", gene_set_id=SET_ID, created_at="2026-09-15T10:00:00Z")

    assert _row_from_experiment(exp)["gene_set_id"] == SET_ID


def test_an_evaluation_started_without_a_set_records_no_set_id() -> None:
    exp = _experiment("exp-2", gene_set_id=None, created_at="2026-09-15T10:00:00Z")

    row = _row_from_experiment(exp)

    assert (row["id"], row["gene_set_id"]) == ("exp-2", None)


def test_the_set_id_survives_the_json_round_trip() -> None:
    exp = _experiment("exp-3", gene_set_id=SET_ID, created_at="2026-09-15T10:00:00Z")

    restored = Experiment.model_validate(exp.model_dump(by_alias=True))

    assert restored.config.gene_set_id == SET_ID


def test_the_set_answers_its_experiments_newest_first() -> None:
    older = _experiment(
        "exp-older", gene_set_id=SET_ID, created_at="2026-09-14T09:00:00Z"
    )
    newer = _experiment(
        "exp-newer", gene_set_id=SET_ID, created_at="2026-09-15T09:00:00Z"
    )

    found = experiments_for_gene_set(
        [older, newer], gene_set_id=SET_ID, user_id=USER_ID
    )

    assert [exp.id for exp in found] == ["exp-newer", "exp-older"]


def test_a_set_with_no_experiment_answers_nothing() -> None:
    other = _experiment(
        "exp-other-set", gene_set_id=OTHER_SET_ID, created_at="2026-09-15T09:00:00Z"
    )

    assert experiments_for_gene_set([other], gene_set_id=SET_ID, user_id=USER_ID) == []


def test_another_user_experiment_on_the_same_set_is_not_returned() -> None:
    mine = _experiment(
        "exp-mine", gene_set_id=SET_ID, created_at="2026-09-15T09:00:00Z"
    )
    theirs = _experiment(
        "exp-theirs",
        gene_set_id=SET_ID,
        created_at="2026-09-15T10:00:00Z",
        user_id=str(OTHER_USER_ID),
    )

    found = experiments_for_gene_set(
        [mine, theirs], gene_set_id=SET_ID, user_id=USER_ID
    )

    assert [exp.id for exp in found] == ["exp-mine"]


def test_an_experiment_of_another_application_is_not_returned() -> None:
    mine = _experiment(
        "exp-mine", gene_set_id=SET_ID, created_at="2026-09-15T09:00:00Z"
    )
    theirs = mine.model_copy(
        update={"id": "exp-other-app", "application_id": "some-other-app"}
    )

    found = experiments_for_gene_set(
        [mine, theirs], gene_set_id=SET_ID, user_id=USER_ID
    )

    assert [exp.id for exp in found] == ["exp-mine"]


def test_an_experiment_with_no_gene_set_is_not_returned() -> None:
    loose = _experiment(
        "exp-loose", gene_set_id=None, created_at="2026-09-15T09:00:00Z"
    )

    assert experiments_for_gene_set([loose], gene_set_id=SET_ID, user_id=USER_ID) == []


def test_a_newer_batch_child_does_not_displace_the_evaluation_of_the_set() -> None:
    """A batch child evaluates one organism, so the set's own run still answers."""
    evaluation = _experiment(
        "exp-evaluation", gene_set_id=SET_ID, created_at="2026-09-14T09:00:00Z"
    )
    child = _experiment(
        "exp-batch-child",
        gene_set_id=SET_ID,
        created_at="2026-09-15T09:00:00Z",
        batch_id="batch_1757930000000",
    )

    found = experiments_for_gene_set(
        [evaluation, child], gene_set_id=SET_ID, user_id=USER_ID
    )

    assert [exp.id for exp in found] == ["exp-evaluation"]


def test_a_set_whose_only_runs_are_batch_children_answers_nothing() -> None:
    children = [
        _experiment(
            "exp-falciparum",
            gene_set_id=SET_ID,
            created_at="2026-09-15T09:00:00Z",
            batch_id="batch_1757930000000",
        ),
        _experiment(
            "exp-vivax",
            gene_set_id=SET_ID,
            created_at="2026-09-15T09:01:00Z",
            batch_id="batch_1757930000000",
        ),
    ]

    assert experiments_for_gene_set(children, gene_set_id=SET_ID, user_id=USER_ID) == []


def test_a_benchmark_child_is_not_an_evaluation_of_the_set() -> None:
    """A benchmark child evaluates one control set, not the set itself."""
    evaluation = _experiment(
        "exp-evaluation", gene_set_id=SET_ID, created_at="2026-09-14T09:00:00Z"
    )
    child = _experiment(
        "exp-benchmark-child",
        gene_set_id=SET_ID,
        created_at="2026-09-15T09:00:00Z",
        benchmark_id="bench_1757930000000",
    )

    found = experiments_for_gene_set(
        [evaluation, child], gene_set_id=SET_ID, user_id=USER_ID
    )

    assert [exp.id for exp in found] == ["exp-evaluation"]
