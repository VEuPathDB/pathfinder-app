"""The comparison part of the evidence facade: running search variants with
and without a control set."""

from pathfinder.services.experiment import scored_comparison, variant_comparison


async def run_variant_comparison(
    site_id: str,
    specs: list[variant_comparison.VariantSpec],
) -> variant_comparison.VariantComparison:
    """Run each variant and compare the result gene sets. Nothing is scored."""
    return await variant_comparison.run_variant_comparison(site_id, specs)


async def run_scored_comparison(
    site_id: str,
    user_id: str | None,
    variants: list[variant_comparison.VariantSpec],
    *,
    positive_controls: list[str],
    negative_controls: list[str],
    objective: str = "mcc",
) -> scored_comparison.ScoredComparison:
    """Run each variant as a scored experiment and rank it by the objective."""
    return await scored_comparison.run_scored_comparison(
        site_id,
        user_id,
        variants,
        positive_controls=positive_controls,
        negative_controls=negative_controls,
        objective=objective,
    )
