"""The comparison part of the evidence facade: running search variants with
and without a control set."""

from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import StrategyAst
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.strategy.operational_spec import StructureNode
from pathfinder.services.experiment import (
    reading_count,
    scored_comparison,
    search_reads,
    variant_comparison,
)


async def run_search_count(
    site_id: str, spec: variant_comparison.VariantSpec
) -> search_reads.SearchCount:
    """How many genes one search returns. No step is created."""
    return await search_reads.search_count(site_id, spec)


async def run_reading_count(
    site_id: str,
    specs: list[variant_comparison.VariantSpec],
    root: StructureNode,
) -> reading_count.CountedReading:
    """A proposal's spec and the genes its plan holds, counted from each search's
    ids when it can be. No step is created."""
    return await reading_count.count_reading(site_id, specs, root)


async def run_search_membership(
    site_id: str, spec: variant_comparison.VariantSpec, gene_ids: list[str]
) -> search_reads.SearchMembership:
    """Which of the gene ids one search holds. No step is created."""
    return await search_reads.search_membership(site_id, spec, gene_ids)


async def run_variant_comparison(
    site_id: str,
    specs: list[variant_comparison.VariantSpec],
) -> variant_comparison.VariantComparison:
    """Run each variant and compare the result gene sets. Nothing is scored."""
    return await variant_comparison.run_variant_comparison(site_id, specs)


async def variant_phyletic_values(
    site_id: str, record_type: str, search_name: str, lists: dict[str, str]
) -> dict[str, ParamValue]:
    """The orthology profile values the two species lists derive."""
    return await variant_comparison.phyletic_values(
        site_id, record_type, search_name, lists
    )


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
