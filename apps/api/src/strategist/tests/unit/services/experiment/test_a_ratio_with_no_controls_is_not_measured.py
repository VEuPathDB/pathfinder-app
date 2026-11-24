from __future__ import annotations

from typing import Any

import pytest

from strategist.ai.tools.standalone import optimization
from strategist.ai.tools.standalone.scored_comparison import _scored_line
from strategist.domain.unread import Unread
from strategist.services.experiment import scored_comparison
from strategist.services.experiment.metrics import (
    compute_confusion_matrix,
    compute_metrics,
)
from strategist.services.experiment.scored_comparison import run_scored_comparison
from strategist.services.experiment.types.experiment import (
    Experiment,
    ExperimentConfig,
)
from strategist.services.experiment.variant_comparison import VariantSpec
from strategist.services.parameter_optimization.config import SweepResult

_NO_NEGATIVES = Unread(reason="no negative controls")


def _positives_only(recovered: int) -> Any:
    return compute_metrics(
        compute_confusion_matrix(
            positive_hits=recovered,
            total_positives=3,
            negative_hits=0,
            total_negatives=0,
        )
    )


def test_a_test_of_positives_alone_measures_recall_only() -> None:
    m = _positives_only(2)

    assert m.sensitivity == pytest.approx(2 / 3)
    assert (
        m.specificity,
        m.precision,
        m.f1_score,
        m.mcc,
        m.balanced_accuracy,
        m.youdens_j,
        m.false_positive_rate,
        m.negative_predictive_value,
    ) == (_NO_NEGATIVES,) * 8


def test_a_result_that_holds_every_control_has_no_mcc() -> None:
    m = compute_metrics(
        compute_confusion_matrix(
            positive_hits=5, total_positives=5, negative_hits=5, total_negatives=5
        )
    )

    assert m.mcc == Unread(reason="the result holds every control")
    assert m.precision == pytest.approx(0.5)


def _experiment(name: str, metrics: Any) -> Experiment:
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


async def test_no_variant_wins_on_an_unmeasured_objective(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    by_search = {
        "SA": _experiment("SA", _positives_only(3)),
        "SB": _experiment("SB", _positives_only(2)),
    }

    async def _run(config: ExperimentConfig, **_kw: Any) -> Experiment:
        return by_search[config.search_name]

    monkeypatch.setattr(scored_comparison, "run_experiment", _run)

    result = await run_scored_comparison(
        "plasmodb",
        "u1",
        [
            VariantSpec(
                label="lenient",
                search_name="SB",
                record_type="transcript",
                parameters={},
            ),
            VariantSpec(
                label="strict",
                search_name="SA",
                record_type="transcript",
                parameters={},
            ),
        ],
        positive_controls=["g1", "g2", "g3"],
        negative_controls=[],
    )

    assert (result.winner_label, result.objective) == ("strict", "sensitivity")
    assert [v.mcc for v in result.variants] == [_NO_NEGATIVES, _NO_NEGATIVES]
    assert _scored_line(result, "mcc") == (
        "2 variants scored, winner strict at sensitivity 1.000; mcc not measured: "
        "no negative controls"
    )


def test_a_sweep_of_positives_alone_tables_its_metrics_as_not_measured() -> None:
    sweep = SweepResult.model_validate(
        {
            "variants": [
                {
                    "variantId": variant,
                    "status": "success",
                    "params": {},
                    "score": recall,
                    "recall": recall,
                    "positive": {"recoveredIds": recovered, "missedIds": missed},
                }
                for variant, recall, recovered, missed in (
                    ("v1", 1.0, ["g1", "g2", "g3"], []),
                    ("v2", 2 / 3, ["g1", "g2"], ["g3"]),
                )
            ],
            "searchName": "GenesWithSignalPeptide",
            "objective": "f1",
            "best": None,
            "controlSet": {"id": "cs-1", "name": "Signal peptide controls"},
        }
    )

    table = optimization.sweep_comparison(sweep)

    assert table.objective == "recall"
    assert [(v.mcc, v.precision, v.f1) for v in table.variants] == [
        (_NO_NEGATIVES, _NO_NEGATIVES, _NO_NEGATIVES)
    ] * 2
