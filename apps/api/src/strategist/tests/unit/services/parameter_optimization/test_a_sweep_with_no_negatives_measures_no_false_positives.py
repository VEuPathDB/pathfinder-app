from __future__ import annotations

import pytest
from veupathdb_mcp.controls import ControlTestResult, PositiveControls

from strategist.domain.evidence import NamedControlSet
from strategist.services.experiment.types import OptimizationObjective
from strategist.services.parameter_optimization.builders import (
    _extract_trial_metrics,
)
from strategist.services.parameter_optimization.config import (
    OptimizationConfig,
    SweepResult,
    SweepVariantResult,
)
from strategist.services.parameter_optimization.scoring import _compute_score

_POSITIVES_ONLY = ControlTestResult(
    positive=PositiveControls(
        recovered_ids=["PF3D7_0100100", "PF3D7_0100200", "PF3D7_0100300"],
        missed_ids=["PF3D7_0100400"],
    )
)


def test_positives_alone_measure_no_precision_and_no_specificity() -> None:
    metrics = _extract_trial_metrics(_POSITIVES_ONLY)

    assert (metrics.recall, metrics.fpr, metrics.specificity, metrics.precision) == (
        0.75,
        None,
        None,
        None,
    )


@pytest.mark.parametrize("objective", ["f1", "mcc", "precision", "specificity"])
def test_positives_alone_rank_by_recall(objective: OptimizationObjective) -> None:
    metrics = _extract_trial_metrics(_POSITIVES_ONLY)

    assert _compute_score(metrics, OptimizationConfig(objective=objective)) == 0.75


def test_a_sweep_with_no_negatives_names_recall_as_its_ranking() -> None:
    trial = SweepVariantResult(
        variant_id="v1", status="success", score=0.75, recall=0.75
    )

    sweep = SweepResult(
        variants=[trial],
        best=None,
        search_name="GenesByTaxon",
        objective="f1",
        control_set=NamedControlSet(id="cs-1", name="kinases"),
    )

    assert (sweep.ranked_by, sweep.false_positives_measured) == ("recall", False)
