"""The checks an export clears before it becomes a strategy step."""

from __future__ import annotations

from pydantic_ai.exceptions import ModelRetry
from veupathdb.eda import EdaAnalysisDetail, differential_expression_computations

from pathfinder.domain.eda_parts import EdaComparison, EdaEffectDirection
from pathfinder.services.eda.compute import VolcanoThresholds, analysis_comparison
from pathfinder.services.eda.direction import (
    caption_verdict,
    direction_sentence,
    sign_sentence,
)


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


def _groups(comparison: EdaComparison) -> str:
    return (
        f"group A ({', '.join(comparison.group_a)}) and group B "
        f"({', '.join(comparison.group_b)})"
    )


def compared_groups(
    analysis: EdaAnalysisDetail,
    thresholds: VolcanoThresholds | None,
    caption: str,
) -> EdaComparison | None:
    """The groups a compute export compares, once its caption agrees with them.

    A one-sided export needs a caption whose first group label is a label of
    the kept group. The subset export compares no groups.
    """
    if thresholds is None:
        return None
    comparison = analysis_comparison(analysis)
    direction = thresholds.effect_direction
    kept = direction_sentence(comparison, direction)
    if direction != "upAndDown" and not caption:
        msg = (
            f'effect_direction="{direction}" needs a caption that names the kept '
            f"group's label first. The compute compares {_groups(comparison)}. "
            f"{sign_sentence(comparison)} This call keeps: {kept}. Nothing was "
            f"written."
        )
        raise ModelRetry(msg)
    verdict = caption_verdict(caption, comparison, direction)
    if verdict == "agrees":
        return comparison
    if verdict == "names_no_group":
        msg = (
            f'The caption "{caption}" names no label of either group: '
            f"{_groups(comparison)}. Write a caption that names the kept "
            f"group's label first. This call keeps: {kept}. Nothing was written."
        )
        raise ModelRetry(msg)
    other = "downOnly" if direction == "upOnly" else "upOnly"
    msg = (
        f'The caption "{caption}" does not agree with '
        f'effect_direction="{direction}", which keeps: {kept}. '
        f"{sign_sentence(comparison)} Nothing was written. Name the kept "
        f"group's label first in the caption, or send "
        f'effect_direction="{other}" to keep the other side.'
    )
    raise ModelRetry(msg)


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
