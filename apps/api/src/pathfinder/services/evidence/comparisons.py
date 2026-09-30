"""The comparison part of the evidence facade: running search variants with
and without a control set."""

from veupathdb.domain.strategy import StrategyAst
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.services.experiment import scored_comparison, variant_comparison


async def run_variant_comparison(
    site_id: str,
    specs: list[variant_comparison.VariantSpec],
) -> variant_comparison.VariantComparison:
    """Run each variant and compare the result gene sets. Nothing is scored."""
    return await variant_comparison.run_variant_comparison(site_id, specs)


async def variant_search_parameters(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    """The parameters a variant's search takes, each with the vocabulary its
    parent values give it."""
    return await variant_comparison.search_parameters(
        site_id, record_type, search_name, context
    )


async def counted_in_place(
    site_id: str,
    comparison: variant_comparison.VariantComparison,
    specs: list[variant_comparison.VariantSpec],
    *,
    strategy: StrategyAst,
    steps: dict[str, str],
) -> variant_comparison.VariantComparison:
    """The comparison with each variant counted at the strategy's result."""
    return await variant_comparison.counted_in_place(
        site_id, comparison, specs, strategy=strategy, steps=steps
    )


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
