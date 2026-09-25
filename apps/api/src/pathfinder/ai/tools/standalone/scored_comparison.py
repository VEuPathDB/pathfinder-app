"""Lead tool: run 2+ search variants as SCORED experiments against a saved
control set, rank by an objective metric (MCC default), and surface a winner
card. The controls-based counterpart to compare_search_variants."""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import DataChunk

from pathfinder.ai.graph.turn_records import ControlTestRun
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._id_arguments import parse_id_argument
from pathfinder.ai.tools.standalone._variant_targets import reject_combine_variants
from pathfinder.domain.evidence import ControlSetEvidence, ControlTestEvidence
from pathfinder.services.evidence.comparisons import run_scored_comparison
from pathfinder.services.evidence.control_sets import get_control_set
from pathfinder.services.experiment.scored_comparison import ScoredComparison
from pathfinder.services.experiment.variant_comparison import VariantSpec

_MIN_VARIANTS = 2


def _filed(controls: list[str], hits: set[str]) -> ControlSetEvidence | None:
    """The controls a variant returned and the rest, or None with no control."""
    ids = list(dict.fromkeys(controls))
    if not ids:
        return None
    return ControlSetEvidence(
        returned=[gene for gene in ids if gene in hits],
        not_returned=[gene for gene in ids if gene not in hits],
    )


def _scored_runs(
    comparison: ScoredComparison,
    *,
    positives: list[str],
    negatives: list[str],
    tool_call_id: str,
) -> list[ControlTestRun]:
    """One control result per variant the comparison scored."""
    runs: list[ControlTestRun] = []
    for variant in comparison.variants:
        hits = set(variant.control_hits)
        positive, negative = _filed(positives, hits), _filed(negatives, hits)
        if variant.error is not None or (positive is None and negative is None):
            continue
        runs.append(
            ControlTestRun(
                tool_call_id=f"{tool_call_id}:{variant.label}",
                origin="scored_comparison",
                evidence=ControlTestEvidence(
                    tested_label=variant.label, positive=positive, negative=negative
                ),
            )
        )
    return runs


def _membership(comparison: ScoredComparison) -> str:
    """Which of the control ids each variant's result holds."""
    return "; ".join(
        f"{v.label} contains {', '.join(v.control_hits) or 'none of them'}"
        for v in comparison.variants
    )


def _summary(comparison: ScoredComparison) -> str:
    scored = [v for v in comparison.variants if v.error is None]
    failed = [v for v in comparison.variants if v.error is not None]
    parts = [f"Ran {len(comparison.variants)} variants against the control set."]
    if scored:
        rows = "; ".join(
            f"{v.label}: MCC={v.mcc}, F1={v.f1}, prec={v.precision}" for v in scored
        )
        winner = comparison.winner_label or "none"
        parts.append(f"Ranked by {comparison.objective}: {rows}. Winner: {winner}.")
    if failed:
        lines = "; ".join(f"{v.label}: {v.error}" for v in failed)
        parts.append(
            f"The scoring failed for {len(failed)} of them - {lines}. "
            "Tell the user the scoring failed and why; do not name another "
            "reason and do not report a score for those variants."
        )
    parts.append(f"Control ids per variant: {_membership(comparison)}.")
    parts.append(
        "Report the winner and the metric trade-offs, then proceed with the "
        "chosen variant."
        if scored
        else "Answer the membership question from the ids above."
    )
    return " ".join(parts)


async def compare_variants_scored(
    ctx: RunContext[LeadDeps],
    variants: list[VariantSpec],
    control_set_id: str,
    objective: str = "mcc",
) -> ToolReturn[ScoredComparison]:
    """Run each variant as a full scored run against a saved control
    set and rank them by ``objective`` (mcc | balanced_accuracy | f1 |
    precision | sensitivity). Use after the user has chosen/built a control
    set (see build_control_set / list_control_sets). Returns per-variant
    metrics + the winning variant as a card. A variant that carries an error
    scored nothing: report that its scoring failed and quote the one line,
    never a different reason. Every variant also carries the control ids its
    result contains, so a membership question is answerable either way.
    """
    runtime = ctx.deps.runtime
    if len(variants) < _MIN_VARIANTS:
        msg = "compare_variants_scored needs at least 2 variants."
        raise ModelRetry(msg)
    reject_combine_variants(variants)

    parsed = parse_id_argument(
        control_set_id, argument="control_set_id", names="control set"
    )
    async with runtime.db_session_factory() as session:
        control_set = await get_control_set(session, parsed, runtime.user_id)

    result = await run_scored_comparison(
        runtime.site_id,
        str(runtime.user_id),
        variants,
        positive_controls=control_set.positive_ids,
        negative_controls=control_set.negative_ids,
        objective=objective,
    )
    ctx.deps.state.turn_markers.record_control_tests(
        _scored_runs(
            result,
            positives=control_set.positive_ids,
            negatives=control_set.negative_ids,
            tool_call_id=ctx.tool_call_id or "",
        )
    )
    chunk = DataChunk(
        type="data-scored-comparison",
        data=result.model_dump(by_alias=True, mode="json"),
    )
    scored = with_summary(
        result,
        _scored_line(result),
        ctx=ctx,
        extra=[chunk],
    )
    scored.content = _summary(result)
    return scored


def _scored_line(comparison: ScoredComparison) -> str:
    """How many variants scored, and which one won."""
    total = len(comparison.variants)
    failed = sum(1 for v in comparison.variants if v.error is not None)
    winner = next(
        (v for v in comparison.variants if v.label == comparison.winner_label),
        None,
    )
    if winner is None:
        if failed:
            return f"scoring failed for {failed} of {total} variants"
        return f"{total} variants scored, no winner"
    score = winner.mcc or 0.0
    return f"{total} variants scored, winner {winner.label} at {score:.3f}"
