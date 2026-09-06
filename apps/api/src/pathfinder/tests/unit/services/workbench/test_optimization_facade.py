from __future__ import annotations

import pytest
from veupathdb.domain.parameters.values import NumberValue, ParamValue, SinglePickValue

from pathfinder.services.parameter_optimization import sweep
from pathfinder.services.parameter_optimization.config import (
    OptimizationConfig,
    ParameterSpec,
    SweepControls,
    SweepTarget,
    SweepVariantResult,
    SweepVariantSpec,
)
from pathfinder.services.workbench import optimization

_TARGET = SweepTarget(
    site_id="plasmodb",
    record_type="transcript",
    search_name="GenesByRNASeqEvidence",
    fixed_parameters={},
)
_CONTROLS = SweepControls(
    controls_search_name="GeneByLocusTag",
    controls_param_name="ds_gene_ids",
    controls_value_format="comma_delimited",
    controls_extra_parameters={},
    positive_controls=["PF3D7_0102600"],
    negative_controls=[],
    id_field=None,
)


def test_the_grid_is_the_cartesian_product_of_the_parameter_space() -> None:
    fixed: dict[str, ParamValue] = {"organism": SinglePickValue(value="pf3d7")}

    variants = optimization.enumerate_variants(
        [
            ParameterSpec(name="fold_change", type="integer", min=2, max=4, step=1),
            ParameterSpec(name="direction", type="categorical", choices=["up", "down"]),
        ],
        fixed,
    )

    assert [v.id for v in variants] == ["v0", "v1", "v2", "v3", "v4", "v5"]
    assert variants[0].params["fold_change"] == NumberValue(value=2.0)
    assert variants[0].params["direction"] == SinglePickValue(value="up")
    assert variants[0].params["organism"] == SinglePickValue(value="pf3d7")


async def test_a_trial_reaches_the_sweep_with_its_target_controls_and_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, str, str]] = []

    async def _run_trial(
        variant: SweepVariantSpec,
        *,
        target: SweepTarget,
        controls: SweepControls,
        score_cfg: OptimizationConfig,
        progress_callback: sweep.ProgressFn | None = None,
    ) -> SweepVariantResult:
        del progress_callback
        seen.append((variant.id, target.search_name, controls.controls_search_name))
        return SweepVariantResult(
            variant_id=variant.id,
            status="success",
            params=variant.params,
            score=0.71 if score_cfg.objective == "f1" else 0.0,
        )

    monkeypatch.setattr(sweep, "run_trial", _run_trial)

    result = await optimization.run_trial(
        SweepVariantSpec(id="v0", params={}),
        target=_TARGET,
        controls=_CONTROLS,
        score_cfg=OptimizationConfig(objective="f1"),
    )

    assert result.score == 0.71
    assert seen == [("v0", "GenesByRNASeqEvidence", "GeneByLocusTag")]
