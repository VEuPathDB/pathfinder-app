"""Export the open EDA analysis into the researcher's strategy as a WDK step."""

from __future__ import annotations

from typing import Literal

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.domain.strategy import StrategyStepNode, subtree_ids
from veupathdb.errors import ValidationError
from veupathdb_mcp import ToolErrorPayload

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._validation_helpers import get_graph
from pathfinder.ai.tools.standalone.strategy_refusals import wdk_refused_the_edit
from pathfinder.ai.tools.standalone.stream_parts import (
    graph_snapshot_chunk,
    strategy_link_chunk,
)
from pathfinder.domain.eda_parts import EdaEffectDirection
from pathfinder.domain.eda_thread import EdaExport
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.operations import AddLeafOp
from pathfinder.domain.strategy.operations.types import (
    AttachIntoSlot,
    AttachNewRoot,
    AttachPoint,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_edit_guard import spec_stated_values
from pathfinder.services.eda.binding import (
    ConversationAnalysisView,
    bound_conversation_analysis,
    read_analysis,
)
from pathfinder.services.eda.compute import NoComputationError, VolcanoThresholds
from pathfinder.services.eda.steps import eda_step_node
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


def _thresholds(
    effect_size_threshold: float | None,
    significance_threshold: float | None,
    effect_direction: EdaEffectDirection,
) -> VolcanoThresholds | None:
    """The volcano cut this call names, or None for the subset export."""
    if effect_size_threshold is None or significance_threshold is None:
        return None
    return VolcanoThresholds(
        effect_size_threshold=effect_size_threshold,
        significance_threshold=significance_threshold,
        effect_direction=effect_direction,
    )


async def bound_analysis(
    ctx: RunContext[LeadDeps],
) -> ConversationAnalysisView | None:
    """The analysis this conversation has open, or None."""
    return await bound_conversation_analysis(
        conversation_id=ctx.deps.state.conversation_id
    )


def _strategy_context(ctx: RunContext[LeadDeps]) -> StrategyMutationContext:
    runtime = ctx.deps.runtime
    spec = ctx.deps.state.domain.operational_spec
    return StrategyMutationContext(
        site_id=runtime.site_id,
        strategy_session=runtime.strategy_session,
        conversation_id=ctx.deps.state.conversation_id,
        db_session_factory=runtime.db_session_factory,
        stated_criteria=(
            frozenset() if spec is None else frozenset(c.id for c in spec.criteria)
        ),
        stated_structure=None if spec is None else spec.structure,
        stated_values={} if spec is None else spec_stated_values(spec),
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


def _attach_point(
    attach_to_step_id: str | None,
    slot: Literal["primary", "secondary"] | None,
) -> AttachPoint:
    if attach_to_step_id is None and slot is None:
        return AttachNewRoot()
    if attach_to_step_id is None:
        msg = (
            f"slot={slot!r} names an input of a combine step, so it needs "
            f"attach_to_step_id. Leave both unset to add the step as a new root."
        )
        raise ModelRetry(msg)
    if slot is None:
        msg = (
            f"attach_to_step_id={attach_to_step_id!r} needs a slot: 'primary' or "
            f"'secondary' names which input of that combine to fill."
        )
        raise ModelRetry(msg)
    return AttachIntoSlot(target_step_id=attach_to_step_id, slot=slot)


def _criterion_note(ctx: RunContext[LeadDeps], step_id: str) -> str:
    """The criterion a step answers, as a parenthetical, or nothing."""
    spec = ctx.deps.state.domain.operational_spec
    if spec is None:
        return ""
    stated = [c.text for c in spec.criteria if c.id == step_id]
    return f" ({stated[0]})" if stated else ""


def _refuse_an_occupied_slot(
    ctx: RunContext[LeadDeps], graph: StrategyGraph, attach: AttachPoint
) -> None:
    """An export fills a free slot, never one that already holds a step.

    A new step holds nothing, so filling an occupied slot would take the step
    that slot holds off the strategy with no delete and no record of the loss.
    """
    if attach.mode != "into-slot":
        return
    target = graph.get_step(attach.target_step_id)
    if target is None:
        return
    occupant = (
        target.primary_input_id
        if attach.slot == "primary"
        else target.secondary_input_id
    )
    if occupant is None:
        return
    msg = (
        f"The {attach.slot} input of {attach.target_step_id} already holds "
        f"{occupant}{_criterion_note(ctx, occupant)}. Exporting into it would "
        f"take {occupant} off the strategy, so nothing was added. Delete "
        f"{occupant} first, or name a slot that is free."
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


def _state_the_exported_step(
    ctx: RunContext[LeadDeps], graph: StrategyGraph, node: StrategyStepNode
) -> None:
    """State the exported step as a criterion of the spec.

    A step wired into the main tree is one the strategy states, so a later
    write is measured against it like any other criterion.
    """
    root_id = graph.primary_root_id()
    if root_id is None or node.id not in subtree_ids(root_id, graph.steps):
        return
    ctx.deps.state.domain.record_criterion(
        Criterion(
            id=node.id,
            text=node.display_name or "the open EDA analysis",
            search_name=node.search_name,
            resolved_params=dict(node.parameters),
            confidence=1.0,
        ),
    )


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


async def create_eda_step(
    ctx: RunContext[LeadDeps],
    *,
    search_name: str | None = None,
    attach_to_step_id: str | None = None,
    slot: Literal["primary", "secondary"] | None = None,
    effect_size_threshold: float | None = None,
    significance_threshold: float | None = None,
    effect_direction: EdaEffectDirection = "upAndDown",
) -> ToolReturn[EdaStepCreated | ToolErrorPayload]:
    """Export the open EDA analysis into the researcher's strategy as a step.

    The step is an ordinary WDK step from then on: it combines, transforms,
    nests and saves like any other, and it appears in the strategy graph the
    researcher is looking at.

    Two exports, and the arguments decide which:

    - The SUBSET's genes: call with no thresholds. Every gene in the filtered
      subset becomes a step.
    - The genes passing a VOLCANO's thresholds: pass ``effect_size_threshold``
      AND ``significance_threshold``. The compute must already be complete -
      call run_eda_compute first and read its summary, so you know how many
      genes you are about to export. ``effect_direction`` selects the up side,
      the down side, or both.

    A gene passes when the absolute effect size is at or above
    ``effect_size_threshold`` and the p-value is at or below
    ``significance_threshold``. Those are the same comparisons the plot uses, so
    the step's count matches the number you told the researcher.

    Leave ``attach_to_step_id`` unset to add the step as a new root. Set it,
    with ``slot``, to wire the step into an existing combine. The slot must be
    free: a slot that already holds a step is refused, because the export would
    take that step off the strategy. Delete it first, or name the free slot.

    Available once ``preview_eda_subset`` has counted the open analysis this
    turn, so the number you export is one you measured.

    Args:
        ctx: Agent run context.
        search_name: A specific EDA-backed search to use. Leave unset to use
            the generic subset or compute search.
        attach_to_step_id: The combine step to wire this into.
        slot: Which input of that combine to fill. It must be empty.
        effect_size_threshold: Minimum absolute effect size to keep.
        significance_threshold: Maximum p-value to keep.
        effect_direction: Which side of the volcano to keep.
    """
    binding = await bound_analysis(ctx)
    if binding is None:
        msg = (
            "No study is open on this conversation. Call open_eda_analysis on "
            "the dataset you want, filter it with set_eda_filters, then export it."
        )
        raise ModelRetry(msg)
    _checked_thresholds(effect_size_threshold, significance_threshold)
    attach = _attach_point(attach_to_step_id, slot)

    analysis = await read_analysis(binding.site_id, analysis_id=binding.analysis_id)
    try:
        plan = eda_step_node(
            analysis,
            dataset_id=binding.dataset_id,
            thresholds=_thresholds(
                effect_size_threshold,
                significance_threshold,
                effect_direction,
            ),
            search_name=search_name,
        )
    except NoComputationError as exc:
        msg = (
            f"{exc} Call run_eda_compute to run the differential expression, "
            f"then export the genes that pass its thresholds."
        )
        raise ModelRetry(msg) from exc
    node = plan.node
    is_compute_backed = plan.is_compute_backed

    session = ctx.deps.runtime.strategy_session
    graph = get_graph(session, None)
    if graph is None:
        title = "No active strategy graph"
        detail = "create_eda_step needs an initialized graph in the session."
        raise ValidationError(title=title, detail=detail)
    _refuse_an_occupied_slot(ctx, graph, attach)

    result = await apply_operations_and_commit(
        deps=_strategy_context(ctx),
        ops=[AddLeafOp(step=node, attach=attach)],
    )
    _state_the_exported_step(ctx, graph, node)
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
        effect_direction=effect_direction if is_compute_backed else None,
        wdk_strategy_id=wdk_strategy_id,
        wdk_url=sync.wdk_url if sync is not None else None,
        guidance=_guidance(wdk_strategy_id, is_compute_backed=is_compute_backed),
    )
    ctx.deps.state.turn_markers.eda_export = created
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
    return with_summary(
        created,
        f"Step {node.id} added to the strategy",
        ctx=ctx,
        extra=metadata,
    )
