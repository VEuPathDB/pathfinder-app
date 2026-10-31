"""The words that state a volcano direction by the groups a compute compares.

A positive effect size is higher in group B, as the EDA volcano app labels
its positive side "Up in" group B. ``upOnly`` keeps group B's side.
"""

from __future__ import annotations

from pathfinder.domain.eda_parts import EdaComparison, EdaEffectDirection


def _named(labels: list[str]) -> str:
    return ", ".join(labels)


def _kept(comparison: EdaComparison, effect_direction: EdaEffectDirection) -> str:
    a = _named(comparison.group_a)
    b = _named(comparison.group_b)
    match effect_direction:
        case "upOnly":
            return f"higher in {b} than in {a}"
        case "downOnly":
            return f"higher in {a} than in {b}"
        case "upAndDown":
            return f"that differ between {a} and {b}"


def sign_sentence(comparison: EdaComparison) -> str:
    """The sign rule of the effect size, with both groups' labels."""
    return (
        f"A positive effect size means the gene is higher in group B "
        f"({_named(comparison.group_b)}) than in group A "
        f"({_named(comparison.group_a)})."
    )


def direction_sentence(
    comparison: EdaComparison, effect_direction: EdaEffectDirection
) -> str:
    """The genes one direction keeps, named by the groups. It names the step."""
    return f"Genes {_kept(comparison, effect_direction)}"


def selection_sentence(
    comparison: EdaComparison,
    effect_direction: EdaEffectDirection,
    *,
    count: int | None,
) -> str:
    """What an export kept, with its count when the site reported one."""
    kept = _kept(comparison, effect_direction)
    if count is None:
        return f"Keeps the genes {kept}."
    return f"Kept {count:,} genes {kept}."
