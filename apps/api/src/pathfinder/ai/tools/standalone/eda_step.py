"""Export the open EDA analysis into the researcher's strategy as a WDK step."""

from __future__ import annotations

from typing import Literal

from assistant_core.graph.tool_summary import with_summary
from pydantic import Field
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.domain.strategy import CombineOp
from veupathdb.eda import EdaAnalysisDetail
from veupathdb.errors import ValidationError
from veupathdb_mcp import ToolErrorPayload

from pathfinder.ai.lead.answered_strategy import the_strategy_now_answers_to
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._eda_step_guard import (
    compared_groups,
    refuse_a_direction_without_a_volcano,
)
from pathfinder.ai.tools.standalone._eda_step_spec import (
    restate_the_structure,
    spec_after_the_replacement,
    state_the_exported_step,
    structure_states_the_graph,
)
from pathfinder.ai.tools.standalone._eda_step_write import export_write
from pathfinder.ai.tools.standalone._validation_helpers import (
    get_graph,
    validation_model_retry,
)
from pathfinder.ai.tools.standalone.strategy_refusals import (
    operation_refused_message,
    wdk_refused_the_edit,
)
from pathfinder.ai.tools.standalone.stream_parts import (
    graph_snapshot_chunk,
    strategy_link_chunk,
)
from pathfinder.domain.eda_parts import EdaEffectDirection
from pathfinder.domain.eda_thread import EdaExport
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.spec_edit_guard import spec_stated_values
from pathfinder.domain.strategy.step_words import criterion_texts
from pathfinder.services.eda.binding import (
    ConversationAnalysisView,
    bound_conversation_analysis,
    read_analysis,
)
from pathfinder.services.eda.compute import NoComputationError, VolcanoThresholds
from pathfinder.services.eda.direction import selection_sentence
from pathfinder.services.eda.gene_subset import (
    NoGeneSubsetError,
    refuse_a_subset_that_selects_no_genes,
)
from pathfinder.services.eda.steps import EdaStepPlan, eda_step_node
from pathfinder.services.strategies.commit import (
    CommitResult,
    apply_operations_and_commit,
)
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.graph_outcome import outcome_for_graph
from pathfinder.services.strategies.sync_state import ensure_sync_state


class EdaStepCreated(EdaExport):
    """What the researcher's strategy now holds, and what to say about it."""

    wdk_strategy_id: int | None = None
    wdk_url: str | None = None
    guidance: str = ""
    # The step this export took the place of, and every step that left with it.
    replaced_step_id: str | None = None
    dropped_step_ids: list[str] = Field(default_factory=list)
    # The operator this export was joined to the strategy's root with, and the
    # combine step that join created, which is the strategy's new root.
    combined_with_root: CombineOp | None = None
    combine_step_id: str | None = None
    # The genes a compute export kept, named by the group they are higher in.
    selection: str | None = None


def _thresholds(
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


async def bound_analysis(
    ctx: RunContext[LeadDeps],
) -> ConversationAnalysisView | None:
    """The analysis this conversation has open, or None."""
    return await bound_conversation_analysis(
        conversation_id=ctx.deps.state.conversation_id
    )


def _strategy_context(
    ctx: RunContext[LeadDeps], spec: OperationalSpec | None
) -> StrategyMutationContext:
    """The context a write runs under, measured against ``spec``."""
    runtime = ctx.deps.runtime
    return StrategyMutationContext(
        site_id=runtime.site_id,
        strategy_session=runtime.strategy_session,
        conversation_id=ctx.deps.state.conversation_id,
        db_session_factory=runtime.db_session_factory,
        stated_criteria=(
            frozenset() if spec is None else frozenset(c.id for c in spec.criteria)
        ),
        stated_structure=None if spec is None else spec.structure,
        criterion_texts={} if spec is None else criterion_texts(spec),
        stated_values={} if spec is None else spec_stated_values(spec),
        user_prompt=ctx.deps.state.user_prompt,
    )


def _checked_thresholds(
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


def _record_the_build(ctx: RunContext[LeadDeps], commit: CommitResult) -> None:
    """Take the exported step as this turn's build, with the sync's counts.

    A commit that did not sync left the step off VEuPathDB: it is a draft on
    the canvas with no size, so the turn records no build and the ledger keeps
    the last one that reached the site.
    """
    sync = commit.sync_result
    if sync is None:
        return
    session = ctx.deps.runtime.strategy_session
    ctx.deps.state.record_build(
        outcome_for_graph(
            graph=session.get_graph(None),
            sync_state=ensure_sync_state(session),
            counts=sync.counts,
            failed_step_ids=commit.failed_step_ids,
            wdk_url=sync.wdk_url,
        ),
    )


def _landed(
    step_id: str,
    replace_step_id: str | None,
    combine_with_root: CombineOp | None,
    root_before: str | None,
) -> str:
    """The one line this export is summarized by."""
    if replace_step_id is not None:
        return f"Step {step_id} replaced {replace_step_id}"
    if combine_with_root is not None:
        return f"Step {step_id} combined with {root_before} ({combine_with_root.value})"
    return f"Step {step_id} added to the strategy"


def _guidance(wdk_strategy_id: int | None, *, is_compute_backed: bool) -> str:
    kind = "the volcano's retained genes" if is_compute_backed else "the subset"
    strategy = (
        f"It is VEuPathDB strategy {wdk_strategy_id}."
        if wdk_strategy_id is not None
        else "VEuPathDB has not accepted it yet."
    )
    return (
        f"The step holds {kind} and behaves like any other step from now on: "
        f"combine it, transform it or save it. {strategy}"
    )


async def _planned_export(
    binding: ConversationAnalysisView,
    analysis: EdaAnalysisDetail,
    *,
    thresholds: VolcanoThresholds | None,
    search_name: str | None,
) -> EdaStepPlan:
    """The step the analysis exports, once it is known to hold genes."""
    try:
        if thresholds is None:
            await refuse_a_subset_that_selects_no_genes(
                binding.site_id, dataset_id=binding.dataset_id, analysis=analysis
            )
    except NoGeneSubsetError as exc:
        raise ModelRetry(exc.message) from exc
    try:
        plan = eda_step_node(
            analysis,
            dataset_id=binding.dataset_id,
            thresholds=thresholds,
            search_name=search_name,
        )
    except NoComputationError as exc:
        msg = (
            f"{exc} Call run_eda_compute to run the differential expression, "
            f"then export the genes that pass its thresholds."
        )
        raise ModelRetry(msg) from exc
    return plan


async def create_eda_step(
    ctx: RunContext[LeadDeps],
    *,
    search_name: str | None = None,
    attach_to_step_id: str | None = None,
    slot: Literal["primary", "secondary"] | None = None,
    replace_step_id: str | None = None,
    combine_with_root: CombineOp | None = None,
    effect_size_threshold: float | None = None,
    significance_threshold: float | None = None,
    effect_direction: EdaEffectDirection | None = None,
    caption: str = "",
) -> ToolReturn[EdaStepCreated | ToolErrorPayload]:
    """Export the open EDA analysis into the researcher's strategy as a step.

    The step is an ordinary WDK step from then on: it combines, transforms,
    nests and saves like any other, and it appears in the strategy graph the
    researcher is looking at.

    Two exports, and the arguments decide which:

    - The SUBSET's genes: call with no thresholds. Every gene in the filtered
      subset becomes a step. The subset needs a filter on the gene entity
      (``has_gene_id`` in describe_eda_study); a subset of samples selects no
      gene and is refused.
    - The genes passing a VOLCANO's thresholds: pass ``effect_size_threshold``
      AND ``significance_threshold``. The compute must already be complete -
      call run_eda_compute first and read its summary, so you know how many
      genes you are about to export. ``effect_direction`` selects a side by
      its group: a positive effect size is higher in group B (the comparison
      group) than in group A (the reference). ``upOnly`` keeps the genes
      higher in group B, ``downOnly`` the genes higher in group A, and
      ``upAndDown`` (the default) both. A direction without both thresholds,
      or on an analysis with no computation, is refused. The step is named by the genes it keeps, and the
      result's ``selection`` says it in the groups' labels: repeat it.

    A gene passes when the absolute effect size is at or above
    ``effect_size_threshold`` and the p-value is at or below
    ``significance_threshold``. Those are the same comparisons the plot uses, so
    the step's count matches the number you told the researcher.

    Leave ``attach_to_step_id`` unset to add the step as a new root. Set it,
    with ``slot``, to wire the step into an existing combine. The slot must be
    free: a slot that already holds a step is refused, because the export would
    take that step off the strategy. Delete it first, or name the free slot.

    Set ``replace_step_id`` to put the export in the place of a step the
    strategy already holds: it takes that step's slot in its parent combine, or
    becomes the root when it replaces the root, and the replaced subtree leaves
    the strategy. Use it for a step this analysis states better. It never
    travels with ``attach_to_step_id`` or ``slot``, which name another target.

    Set ``combine_with_root`` to join the export to the strategy the researcher
    already has: the export is added and a new combine over the old root and
    the export becomes the root, which is how a step is added to a result.
    INTERSECT keeps the genes both hold, UNION keeps either, MINUS drops the
    export's genes from the result. It needs a strategy with one root, and it
    names the whole placement, so it travels with none of the three above.

    A one-sided export needs ``caption``: the genes it keeps, naming the kept
    group's label first ("Genes higher in 24h pbm than in 18h pbm"). A caption
    that names no group label, or whose first label is the other group's, is
    refused and nothing is written.

    Available once ``preview_eda_subset`` has counted the open analysis, on
    this message or an earlier one, so the number you export is one the thread
    measured.

    Args:
        ctx: Agent run context.
        search_name: A specific EDA-backed search to use. Leave unset to use
            the generic subset or compute search.
        attach_to_step_id: The combine step to wire this into.
        slot: Which input of that combine to fill. It must be empty.
        replace_step_id: The step this export takes the place of.
        combine_with_root: The operator to join the export to the root with.
        effect_size_threshold: Minimum absolute effect size to keep.
        significance_threshold: Maximum p-value to keep.
        effect_direction: upOnly keeps group B's side, downOnly group A's.
        caption: The genes a one-sided export keeps, kept group named first.
            Required for upOnly and downOnly.
    """
    binding = await bound_analysis(ctx)
    if binding is None:
        msg = (
            "No study is open on this conversation. Call open_eda_analysis on "
            "the dataset you want, filter it with set_eda_filters, then export it."
        )
        raise ModelRetry(msg)
    _checked_thresholds(effect_size_threshold, significance_threshold)

    analysis = await read_analysis(binding.site_id, analysis_id=binding.analysis_id)
    direction: EdaEffectDirection = effect_direction or "upAndDown"
    thresholds = _thresholds(
        analysis, effect_size_threshold, significance_threshold, effect_direction
    )
    plan = await _planned_export(
        binding, analysis, thresholds=thresholds, search_name=search_name
    )
    comparison = compared_groups(analysis, thresholds, caption)
    node = plan.node
    is_compute_backed = plan.is_compute_backed

    session = ctx.deps.runtime.strategy_session
    graph = get_graph(session, None)
    if graph is None:
        title = "No active strategy graph"
        detail = "create_eda_step needs an initialized graph in the session."
        raise ValidationError(title=title, detail=detail)
    root_before = graph.primary_root_id()
    write = export_write(
        ctx,
        graph,
        node,
        attach_to_step_id=attach_to_step_id,
        slot=slot,
        replace_step_id=replace_step_id,
        combine_with_root=combine_with_root,
    )

    restate = structure_states_the_graph(ctx, graph)
    stated = (
        ctx.deps.state.domain.operational_spec
        if replace_step_id is None
        else spec_after_the_replacement(ctx, graph, node, replace_step_id)
    )

    try:
        result = await apply_operations_and_commit(
            deps=_strategy_context(ctx, stated), ops=write.ops
        )
    except ValidationError as exc:
        raise validation_model_retry(exc, searchName=node.search_name) from exc
    except ApplyError as exc:
        msg = operation_refused_message(str(exc), wrote="export")
        raise ModelRetry(msg) from exc
    if replace_step_id is None:
        state_the_exported_step(ctx, graph, node)
    else:
        ctx.deps.state.domain.operational_spec = stated
    if restate:
        restate_the_structure(ctx, graph)
    the_strategy_now_answers_to(
        ctx.deps.state, ctx.deps.state.domain.operational_spec, graph
    )
    sync = result.sync_result
    metadata: list[DataChunk] = [graph_snapshot_chunk(session, graph)]
    if sync is not None and sync.wdk_url is not None:
        metadata.append(
            strategy_link_chunk(
                strategy_id=graph.id,
                url=sync.wdk_url,
                title=graph.name,
            ),
        )
    wdk_strategy_id = sync.wdk_strategy_id if sync is not None else None
    created = EdaStepCreated(
        search_name=node.search_name,
        step_id=node.id,
        dataset_id=binding.dataset_id,
        analysis_id=binding.analysis_id,
        is_compute_backed=is_compute_backed,
        effect_size_threshold=effect_size_threshold,
        significance_threshold=significance_threshold,
        effect_direction=direction if is_compute_backed else None,
        wdk_strategy_id=wdk_strategy_id,
        wdk_url=sync.wdk_url if sync is not None else None,
        guidance=_guidance(wdk_strategy_id, is_compute_backed=is_compute_backed),
        replaced_step_id=replace_step_id,
        dropped_step_ids=list(result.dropped_step_ids),
        combined_with_root=combine_with_root,
        combine_step_id=None if write.combine is None else write.combine.step.id,
        selection=(
            None
            if comparison is None
            else selection_sentence(
                comparison,
                direction,
                count=None if sync is None else sync.counts.get(node.id),
            )
        ),
    )
    ctx.deps.state.turn_markers.eda_export = created
    ctx.deps.state.turn_markers.edited = True
    _record_the_build(ctx, result)
    refusal = wdk_refused_the_edit(result)
    if refusal is not None:
        return with_summary(
            refusal,
            f"VEuPathDB refused the step for {node.id}",
            ctx=ctx,
            status="warn",
            extra=metadata,
        )
    landed = _landed(node.id, replace_step_id, combine_with_root, root_before)
    return with_summary(created, landed, ctx=ctx, extra=metadata)
