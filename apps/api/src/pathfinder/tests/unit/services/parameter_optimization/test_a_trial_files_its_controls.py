"""A sweep trial keeps each control it was given, filed as the setting returned it."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb_mcp.controls import (
    ControlTargetData,
    ControlTestResult,
    NegativeControls,
    PositiveControls,
)

from pathfinder.services.parameter_optimization import sweep
from pathfinder.services.parameter_optimization.config import (
    OptimizationConfig,
    SweepControls,
    SweepTarget,
    SweepVariantSpec,
)

_POSITIVE = PositiveControls(
    recovered_ids=["PF3D7_0102600", "PF3D7_0709000"], missed_ids=["PF3D7_1133400"]
)
_NEGATIVE = NegativeControls(admitted_ids=[], excluded_ids=["TGME49_205250"])


async def test_the_trial_carries_the_lists_its_counts_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def measured(config: Any, **_controls: Any) -> ControlTestResult:
        del config
        return ControlTestResult(
            target=ControlTargetData(estimated_size=132),
            positive=_POSITIVE,
            negative=_NEGATIVE,
        )

    monkeypatch.setattr(sweep, "run_positive_negative_controls", measured)

    trial = await sweep.run_trial(
        SweepVariantSpec(id="v3"),
        target=SweepTarget(
            site_id="plasmodb",
            record_type="transcript",
            search_name="GenesByMolecularWeight",
            fixed_parameters={},
        ),
        controls=SweepControls(
            controls_search_name="GeneByLocusTag",
            controls_param_name="ds_gene_ids",
            controls_value_format="newline",
            controls_extra_parameters={},
            positive_controls=[*_POSITIVE.recovered_ids, *_POSITIVE.missed_ids],
            negative_controls=_NEGATIVE.excluded_ids,
            id_field=None,
        ),
        score_cfg=OptimizationConfig(),
    )

    assert (trial.positive, trial.negative, trial.positive_hits) == (
        _POSITIVE,
        _NEGATIVE,
        2,
    )
