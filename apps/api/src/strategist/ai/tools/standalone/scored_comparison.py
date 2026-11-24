"""Lead tool: run 2+ search variants as SCORED experiments against a saved
control set, rank by an objective metric (MCC default), and surface a winner
card. The controls-based counterpart to compare_search_variants."""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import DataChunk

from strategist.ai.graph.turn_records import ControlTestRun
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.tools.standalone._id_arguments import ControlSetId
from strategist.ai.tools.standalone._variant_targets import (
    ComparedVariants,
    checked_variants,
    reject_combine_variants,
)
from strategist.ai.tools.standalone.saved_control_sets import (
    ATTACH_A_SET,
    unattached_set,
)
from strategist.domain.evidence import (
    ControlSetEvidence,
    ControlTestEvidence,
    NamedControlSet,
)
from strategist.domain.unread import Unread
from strategist.services.evidence.comparisons import run_scored_comparison
from strategist.services.evidence.control_sets import get_control_set
from strategist.services.experiment.scored_comparison import (
    Objective,
    ScoredComparison,
    ranked_winner,
)


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
    control_set: NamedControlSet,
    tool_call_id: str,
) -> list[ControlTestRun]:
    """One control result per variant the comparison scored."""
    runs: list[ControlTestRun] = []
    for variant in comparison.variants:
        match variant.control_hits:
            case Unread():
                continue
            case list() as found:
                hits = set(found)
        positive, negative = _filed(positives, hits), _filed(negatives, hits)
        if variant.error is not None or (positive is None and negative is None):
            continue
        runs.append(
            ControlTestRun(
                tool_call_id=f"{tool_call_id}:{variant.label}",
                origin="scored_comparison",
                evidence=ControlTestEvidence(
                    tested_label=variant.label,
                    control_set=control_set,
                    positive=positive,
                    negative=negative,
                ),
            )
        )
    return runs


async def compare_variants_scored(
    ctx: RunContext[LeadDeps],
    variants: ComparedVariants,
    control_set_id: ControlSetId,
    objective: Objective = "mcc",
) -> ToolReturn[ScoredComparison]:
    """Run each variant as a full scored run against a saved control
    set and rank them by ``objective`` (mcc | balanced_accuracy | f1 |
    precision | sensitivity). The set is one attached to this conversation
    (``build_control_set`` or ``use_control_set``). Returns per-variant
    metrics + the winning variant as a card. A variant that carries an error
    scored nothing: report that its scoring failed and quote the one line,
    never a different reason. Every variant also carries the control ids its
    result contains, so a membership question is answerable either way. A
    pick a variant leaves out runs at the site's default.
    """
    runtime = ctx.deps.runtime
    reject_combine_variants(variants)
    refused = unattached_set(str(control_set_id), ctx.deps.state.domain.control_sets)
    if refused is not None:
        msg = f"{refused} {ATTACH_A_SET}"
        raise ModelRetry(msg)
    specs = await checked_variants(
        runtime.strategy_session, variants, ctx.deps.resolving()
    )

    async with runtime.db_session_factory() as session:
        control_set = await get_control_set(session, control_set_id, runtime.user_id)

    result = await run_scored_comparison(
        runtime.site_id,
        str(runtime.user_id),
        specs,
        positive_controls=control_set.positive_ids,
        negative_controls=control_set.negative_ids,
        objective=objective,
    )
    ctx.deps.state.turn_markers.record_control_tests(
        _scored_runs(
            result,
            positives=control_set.positive_ids,
            negatives=control_set.negative_ids,
            control_set=NamedControlSet(id=control_set.id, name=control_set.name),
            tool_call_id=ctx.tool_call_id or "",
        )
    )
    chunk = DataChunk(
        type="data-scored-comparison",
        data=result.model_dump(by_alias=True, mode="json"),
    )
    return with_summary(
        result,
        _scored_line(result, objective),
        ctx=ctx,
        extra=[chunk],
    )


def _unread_memberships(comparison: ScoredComparison) -> str:
    unread = [
        v.label for v in comparison.variants if isinstance(v.control_hits, Unread)
    ]
    return f"; membership not read for {', '.join(unread)}" if unread else ""


def _scored_line(comparison: ScoredComparison, objective: Objective) -> str:
    """How many variants scored, which one won and by which metric, why the
    objective was not measured when it was not, and whose membership was not
    read."""
    total = len(comparison.variants)
    failed = sum(1 for v in comparison.variants if v.error is not None)
    unread = _unread_memberships(comparison)
    ranking = ranked_winner(comparison.variants, objective)
    match ranking.unmeasured:
        case Unread(reason=reason):
            why = f"; {objective} not measured: {reason}"
        case None:
            why = ""
    if ranking.winner is None or ranking.score is None:
        if failed:
            return f"scoring failed for {failed} of {total} variants{why}{unread}"
        return f"{total} variants scored, no winner{why}{unread}"
    return (
        f"{total} variants scored, winner {ranking.winner.label} at "
        f"{ranking.metric} {ranking.score:.3f}{why}{unread}"
    )
