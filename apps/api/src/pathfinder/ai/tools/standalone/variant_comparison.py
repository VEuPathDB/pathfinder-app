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
from pathfinder.ai.tools.standalone._variant_targets import (
    checked_variants,
    reject_combine_variants,
)
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.evidence.comparisons import (
    counted_in_place,
    run_variant_comparison,
)
from pathfinder.services.experiment.variant_comparison import (
    VariantComparison,
    VariantInput,
    VariantSpec,
)

_MIN_VARIANTS = 2


def _steps_running(
    session: StrategySession, variants: list[VariantSpec]
) -> dict[str, str]:
    """The one step of the strategy that runs each variant's search, by label."""
    graph = session.get_graph(None)
    if graph is None:
        return {}
    running = {
        v.label: [
            sid for sid, s in graph.steps.items() if s.search_name == v.search_name
        ]
        for v in variants
    }
    return {label: steps[0] for label, steps in running.items() if len(steps) == 1}


async def compare_search_variants(
    ctx: RunContext[LeadDeps],
    variants: list[VariantInput],
) -> ToolReturn[VariantComparison]:
    """Run 2+ search-config variants and compare how their results differ.

    Use this when the user chose to "try both" / sweep a parameter across
    values / ablate a step - instead of committing to one plan. Each variant
    runs as an anonymous WDK report (no step or strategy is created, so the
    user's workspace is untouched). Returns result sizes, pairwise overlap,
    and the genes unique to each variant, each sampled gene with the product
    its record names, rendered as a comparison card. A
    variant of a search one step of the strategy runs is also counted in the
    strategy's result with the variant in place (``resultCount``), which is
    the count to answer "how many of the result would remain" from. Each
    variant takes only parameters its search takes. A pick a variant leaves
    out runs at the site's default (for text Fields, every field).

    Provide at least two variants; each is one search with one set of
    parameter values, given a short human ``label`` (e.g. "2-fold",
    "5-fold"). This does NOT score or pick a winner; the user judges from
    the differences.

    If a winner matters, prefer ``compare_variants_scored``: given a control
    set attached to this conversation (``build_control_set`` /
    ``use_control_set``) it runs the same variants, scores each against known
    positives and negatives, and ranks them by MCC. Use this unscored tool
    when no control set is attached or the user only wants to see how the
    results differ.
    """
    if len(variants) < _MIN_VARIANTS:
        msg = (
            "compare_search_variants needs at least 2 variants to compare. "
            "Give each variant a label and its search + parameter values."
        )
        raise ModelRetry(msg)
    reject_combine_variants(variants)
    site_id = ctx.deps.runtime.site_id
    specs = await checked_variants(ctx.deps.runtime.strategy_session, variants)

    comparison = await run_variant_comparison(site_id, specs)
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
    session = ctx.deps.runtime.strategy_session
    graph = session.get_graph(None)
    strategy = None if graph is None else graph.to_strategy_ast()
    steps = _steps_running(session, specs)
    if strategy is not None and steps:
        comparison = await counted_in_place(
            site_id, comparison, specs, strategy=strategy, steps=steps
        )
    ctx.deps.state.turn_markers.record_comparison(comparison.fact())
    chunk = DataChunk(
        type="data-variant-comparison",
        data=comparison.model_dump(by_alias=True, mode="json"),
    )
    return with_summary(
        comparison,
        _variant_line(comparison),
        ctx=ctx,
        extra=[chunk],
    )


def _variant_line(comparison: VariantComparison) -> str:
    """The variant that returned the most genes, and how many ran."""
    scored = [v for v in comparison.variants if v.error is None]
    if not scored:
        return f"{len(comparison.variants)} variants, none ran"
    best = max(scored, key=lambda v: v.gene_count)
    return (
        f"{len(comparison.variants)} variants: {best.label} {best.gene_count:,} genes"
    )
