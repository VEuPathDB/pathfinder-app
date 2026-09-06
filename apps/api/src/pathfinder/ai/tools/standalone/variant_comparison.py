"""Lead tool: run several search-config variants and compare their result
gene sets in-conversation (exploratory, no control sets). Routes a user's
"try both / sweep this value / ablate that step" choice into a real run."""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import DataChunk

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._variant_targets import reject_combine_variants
from pathfinder.services.experiment.variant_comparison import (
    VariantComparison,
    VariantSpec,
)
from pathfinder.services.workbench.comparisons import run_variant_comparison

_MIN_VARIANTS = 2


def _summary(comparison: VariantComparison) -> str:
    sizes = "; ".join(
        f"{v.label}: {v.gene_count} genes ({v.unique_count} unique)"
        for v in comparison.variants
        if v.error is None
    )
    failed = "; ".join(
        f"{v.label} failed: {v.error}"
        for v in comparison.variants
        if v.error is not None
    )
    fail_note = f" Some variants failed - {failed}." if failed else ""
    overlaps = "; ".join(
        f"{o.a} vs {o.b}: {o.shared} shared (Jaccard {o.jaccard})"
        for o in comparison.overlaps
    )
    note = (
        " (result sets were large; overlap figures are lower bounds)"
        if (comparison.truncated)
        else ""
    )
    return (
        f"Ran {len(comparison.variants)} variants. Sizes - {sizes}. "
        f"Overlap - {overlaps}.{note}{fail_note} Summarize the trade-off for "
        "the user and ask which to proceed with (no scoring - no controls)."
    )


async def compare_search_variants(
    ctx: RunContext[LeadDeps],
    variants: list[VariantSpec],
) -> ToolReturn[VariantComparison]:
    """Run 2+ search-config variants and compare how their results differ.

    Use this when the user chose to "try both" / sweep a parameter across
    values / ablate a step - instead of committing to one plan. Each variant
    runs as an anonymous WDK report (no step or strategy is created, so the
    user's workspace is untouched). Returns result sizes, pairwise overlap,
    and the genes unique to each variant, rendered as a comparison card.

    Provide at least two variants; each is one search with one set of
    parameter values, given a short human ``label`` (e.g. "2-fold",
    "5-fold"). This does NOT score or pick a winner; the user judges from
    the differences.

    If a winner matters, prefer ``compare_variants_scored``: given a control
    set (see ``build_control_set`` / ``list_control_sets``) it runs the same
    variants, scores each against known positives and negatives, and ranks
    them by MCC. Use this unscored tool when no control set exists or the
    user only wants to see how the results differ.
    """
    if len(variants) < _MIN_VARIANTS:
        msg = (
            "compare_search_variants needs at least 2 variants to compare. "
            "Give each variant a label and its search + parameter values."
        )
        raise ModelRetry(msg)
    reject_combine_variants(variants)

    comparison = await run_variant_comparison(ctx.deps.runtime.site_id, variants)
    if all(v.error is not None for v in comparison.variants):
        failures = "; ".join(
            f"{v.label}: {v.error}" for v in comparison.variants if v.error
        )
        msg = (
            f"Every variant failed to run - {failures}. Check each variant's "
            "search_name and that all REQUIRED parameters are provided with "
            "valid values, then retry."
        )
        raise ModelRetry(msg)
    chunk = DataChunk(
        type="data-variant-comparison",
        data=comparison.model_dump(by_alias=True, mode="json"),
    )
    ran = with_summary(
        comparison,
        _variant_line(comparison),
        ctx=ctx,
        extra=[chunk],
    )
    ran.content = _summary(comparison)
    return ran


def _variant_line(comparison: VariantComparison) -> str:
    """The variant that returned the most genes, and how many ran."""
    scored = [v for v in comparison.variants if v.error is None]
    if not scored:
        return f"{len(comparison.variants)} variants, none ran"
    best = max(scored, key=lambda v: v.gene_count)
    return (
        f"{len(comparison.variants)} variants: {best.label} {best.gene_count:,} genes"
    )
