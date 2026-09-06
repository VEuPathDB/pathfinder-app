from __future__ import annotations

import pytest

from pathfinder.services.experiment import scored_comparison, variant_comparison
from pathfinder.services.experiment.scored_comparison import (
    ScoredComparison,
    ScoredVariant,
)
from pathfinder.services.experiment.variant_comparison import (
    VariantComparison,
    VariantResult,
    VariantSpec,
)
from pathfinder.services.workbench import comparisons

_SPECS = [
    VariantSpec(label="2-fold", search_name="GenesByRNASeq", parameters={}),
    VariantSpec(label="5-fold", search_name="GenesByRNASeq", parameters={}),
]


async def test_the_unscored_comparison_reaches_the_service_with_its_specs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, list[str]]] = []

    async def _run(site_id: str, specs: list[VariantSpec]) -> VariantComparison:
        seen.append((site_id, [s.label for s in specs]))
        return VariantComparison(
            variants=[
                VariantResult(
                    label="2-fold",
                    search_name="GenesByRNASeq",
                    gene_count=132,
                    unique_count=7,
                    sample_unique_genes=["PF3D7_0102600"],
                )
            ],
            overlaps=[],
        )

    monkeypatch.setattr(variant_comparison, "run_variant_comparison", _run)

    comparison = await comparisons.run_variant_comparison("plasmodb", _SPECS)

    assert [v.gene_count for v in comparison.variants] == [132]
    assert seen == [("plasmodb", ["2-fold", "5-fold"])]


async def test_the_scored_comparison_forwards_the_controls_and_the_objective(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, str | None, list[str], list[str], str]] = []

    async def _run(
        site_id: str,
        user_id: str | None,
        variants: list[VariantSpec],
        *,
        positive_controls: list[str],
        negative_controls: list[str],
        objective: str = "mcc",
    ) -> ScoredComparison:
        del variants
        seen.append((site_id, user_id, positive_controls, negative_controls, objective))
        return ScoredComparison(
            variants=[
                ScoredVariant(label="2-fold", search_name="GenesByRNASeq", mcc=0.62)
            ],
            winner_label="2-fold",
            objective=objective,
        )

    monkeypatch.setattr(scored_comparison, "run_scored_comparison", _run)

    comparison = await comparisons.run_scored_comparison(
        "plasmodb",
        "user-1",
        _SPECS,
        positive_controls=["PF3D7_0102600"],
        negative_controls=["PF3D7_0107600"],
        objective="f1",
    )

    assert comparison.winner_label == "2-fold"
    assert seen == [("plasmodb", "user-1", ["PF3D7_0102600"], ["PF3D7_0107600"], "f1")]
