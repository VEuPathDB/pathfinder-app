"""The checks an export clears before it becomes a strategy step."""

from __future__ import annotations

from pydantic_ai.exceptions import ModelRetry
from veupathdb.eda import EdaAnalysisDetail, differential_expression_computations

from pathfinder.domain.eda_parts import EdaComparison, EdaEffectDirection
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.eda.compute import VolcanoThresholds, analysis_comparison
from pathfinder.services.eda.export import exported_dataset


def refuse_a_direction_without_a_volcano(
    analysis: EdaAnalysisDetail,
    *,
    effect_direction: EdaEffectDirection | None,
    has_thresholds: bool,
) -> None:
    """A direction selects a side of a computed volcano, so it needs both."""
    if effect_direction is None:
        return
    if not differential_expression_computations(analysis.descriptor):
        msg = (
            f'effect_direction="{effect_direction}" selects a side of a '
            f"comparison, and the open analysis holds 0 comparisons. Nothing "
            f"was written. Call run_eda_compute to run the comparison, then "
            f"export with effect_size_threshold, significance_threshold and "
            f"effect_direction."
        )
        raise ModelRetry(msg)
    if not has_thresholds:
        msg = (
            f'effect_direction="{effect_direction}" selects a side of the '
            f"volcano, so it needs effect_size_threshold and "
            f"significance_threshold. Send both, or leave effect_direction unset "
            f"to export the subset. Nothing was written."
        )
        raise ModelRetry(msg)


def compared_groups(
    analysis: EdaAnalysisDetail, thresholds: VolcanoThresholds | None
) -> EdaComparison | None:
    """The groups a compute export compares. The subset export compares none."""
    if thresholds is None:
        return None
    return analysis_comparison(analysis)


def refuse_half_a_cut(
    effect_size_threshold: float | None,
    significance_threshold: float | None,
) -> None:
    """Both thresholds or neither. The bridge plugin requires both keys."""
    if effect_size_threshold is not None and significance_threshold is None:
        msg = (
            "A volcano export needs significance_threshold as well as "
            "effect_size_threshold. Send both, or send neither to export the "
            "whole subset."
        )
        raise ModelRetry(msg)
    if significance_threshold is not None and effect_size_threshold is None:
        msg = (
            "A volcano export needs effect_size_threshold as well as "
            "significance_threshold. Send both, or send neither to export the "
            "whole subset."
        )
        raise ModelRetry(msg)


def volcano_thresholds(
    analysis: EdaAnalysisDetail,
    effect_size_threshold: float | None,
    significance_threshold: float | None,
    effect_direction: EdaEffectDirection | None,
) -> VolcanoThresholds | None:
    """The volcano cut this call names, or None for the subset export."""
    has_thresholds = (
        effect_size_threshold is not None and significance_threshold is not None
    )
    refuse_a_direction_without_a_volcano(
        analysis, effect_direction=effect_direction, has_thresholds=has_thresholds
    )
    if effect_size_threshold is None or significance_threshold is None:
        return None
    return VolcanoThresholds(
        effect_size_threshold=effect_size_threshold,
        significance_threshold=significance_threshold,
        effect_direction=effect_direction or "upAndDown",
    )


def refuse_a_recut_of_another_dataset(
    graph: StrategyGraph, replace_step_id: str, dataset_id: str
) -> None:
    """An export reads the open analysis, so it takes no export of another
    dataset's place."""
    exported = exported_dataset(graph, replace_step_id)
    if exported is None or exported == dataset_id:
        return
    msg = (
        f"{replace_step_id} exports an analysis of dataset {exported}, and the open "
        f"analysis is on dataset {dataset_id}: an export reads the open analysis, "
        f"so it cannot take that step's place. Open the analysis on {exported} to "
        "recut it, or name a step this analysis exports."
    )
    raise ModelRetry(msg)
