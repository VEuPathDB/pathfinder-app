"""run_scored_comparison runs a full experiment per variant against controls,
ranks by the objective metric (MCC default), names a winner, and tolerates a
failing variant. run_experiment is mocked — no live WDK.
"""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKAnswer, WDKAnswerMeta

from pathfinder.services.experiment import scored_comparison
from pathfinder.services.experiment.metrics import (
    compute_confusion_matrix,
    compute_metrics,
)
from pathfinder.services.experiment.scored_comparison import run_scored_comparison
from pathfinder.services.experiment.types.experiment import (
    Experiment,
    ExperimentConfig,
)
from pathfinder.services.experiment.variant_comparison import VariantSpec


def _metrics(pos_hits: int, neg_hits: int) -> Any:
    cm = compute_confusion_matrix(
        positive_hits=pos_hits,
        total_positives=10,
        negative_hits=neg_hits,
        total_negatives=10,
    )
    return compute_metrics(cm)


def _exp(name: str, metrics: Any) -> Experiment:
    return Experiment(
        id=f"exp_{name}",
        config=ExperimentConfig(
            site_id="plasmodb",
            record_type="transcript",
            search_name=name,
            parameters={},
            positive_controls=[],
            negative_controls=[],
            controls_search_name="GeneByLocusTag",
            controls_param_name="ds_gene_ids",
        ),
        status="completed",
        metrics=metrics,
    )


def _variants() -> list[VariantSpec]:
    return [
        VariantSpec(label="lenient", search_name="SA", parameters={}),
        VariantSpec(label="strict", search_name="SB", parameters={}),
    ]


@pytest.mark.asyncio
async def test_ranks_by_mcc_and_names_winner(monkeypatch: pytest.MonkeyPatch) -> None:
    # SA: 8/2 -> mcc 0.6 ; SB: 10/0 -> mcc 1.0 -> SB wins.
    by_search = {
        "SA": _exp("SA", _metrics(8, 2)),
        "SB": _exp("SB", _metrics(10, 0)),
    }

    async def _run(config: ExperimentConfig, **_kw: Any) -> Experiment:
        return by_search[config.search_name]

    monkeypatch.setattr(scored_comparison, "run_experiment", _run)

    result = await run_scored_comparison(
        "plasmodb",
        "u1",
        _variants(),
        positive_controls=["g1"],
        negative_controls=["n1"],
    )
    assert result.winner_label == "strict"
    by_label = {v.label: v for v in result.variants}
    assert by_label["lenient"].mcc is not None
    assert abs(by_label["lenient"].mcc - 0.6) < 1e-9
    assert abs((by_label["strict"].mcc or 0.0) - 1.0) < 1e-9


@pytest.mark.asyncio
async def test_failing_variant_excluded_from_ranking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run(config: ExperimentConfig, **_kw: Any) -> Experiment:
        if config.search_name == "SB":
            msg = "WDK exploded"
            raise WDKError(msg)
        return _exp("SA", _metrics(7, 1))

    async def _search(site_id: str, spec: VariantSpec) -> WDKAnswer:
        del site_id, spec
        return WDKAnswer(meta=WDKAnswerMeta(total_count=0), records=[])

    monkeypatch.setattr(scored_comparison, "run_experiment", _run)
    monkeypatch.setattr(scored_comparison, "run_variant_search", _search)

    result = await run_scored_comparison(
        "plasmodb",
        "u1",
        _variants(),
        positive_controls=["g1"],
        negative_controls=["n1"],
    )
    assert result.winner_label == "lenient"  # the only one that scored
    by_label = {v.label: v for v in result.variants}
    assert by_label["strict"].error is not None
    assert "WDK exploded" in by_label["strict"].error


@pytest.mark.asyncio
async def test_objective_can_be_precision(monkeypatch: pytest.MonkeyPatch) -> None:
    # SA higher precision, SB higher mcc -> winner depends on objective.
    by_search = {
        "SA": _exp("SA", _metrics(5, 0)),  # precision 1.0
        "SB": _exp("SB", _metrics(10, 2)),  # precision 10/12
    }

    async def _run(config: ExperimentConfig, **_kw: Any) -> Experiment:
        return by_search[config.search_name]

    monkeypatch.setattr(scored_comparison, "run_experiment", _run)

    result = await run_scored_comparison(
        "plasmodb",
        "u1",
        _variants(),
        positive_controls=["g1"],
        negative_controls=["n1"],
        objective="precision",
    )
    assert result.winner_label == "lenient"  # SA, precision 1.0
