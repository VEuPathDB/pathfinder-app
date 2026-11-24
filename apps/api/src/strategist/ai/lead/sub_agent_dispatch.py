"""The Lead's build and recovery dispatch tools.

The declarative build of the operational spec, and the recovery pass a failed
build re-enters.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from assistant_core.graph.emit import emit_chunk
from langgraph.config import get_stream_writer
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import StrategyStepNode, pushable_root_id, rebuild_tree
from veupathdb.errors import VEuPathDBError

from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.lead.answered_strategy import (
    live_tree,
    the_strategy_now_answers_to,
    the_thread_wrote_the_strategy,
)
from strategist.ai.lead.build_messages import (
    build_not_ready_message,
    build_would_replace_the_strategy,
    organism_unnamed_message,
    round_trip_not_kept_message,
    structure_does_not_convert_message,
)
from strategist.ai.lead.deltas import ExecuteDelta, RecoveryDelta
from strategist.ai.lead.dispatch_context import (
    agent_deps_for,
    defer_dispatch,
    dispatch_call_id,
)
from strategist.ai.lead.dispatch_messages import option_binds_no_step_message
from strategist.ai.lead.sub_agent_stream import (
    PhaseRun,
    SubAgentApprovalWait,
    SubAgentResume,
    stream_sub_agent,
)
from strategist.ai.lead.sub_agent_tools import LeadDeps, apply_agent_state
from strategist.ai.lead.unsaved_set import result_not_saved
from strategist.ai.tools.standalone.graph_helpers import derive_strategy_name
from strategist.ai.tools.standalone.strategy_refusals import departures_refused
from strategist.ai.tools.standalone.stream_parts import graph_snapshot_chunk
from strategist.domain.strategy.build_outcome import BuildOutcome
from strategist.domain.strategy.computed_groups import noted_description
from strategist.domain.strategy.operational_spec import (
    OperationalSpec,
)
from strategist.domain.strategy.operations.apply import ApplyError
from strategist.domain.strategy.organism_picks import asked_organisms
from strategist.domain.strategy.orthology import (
    OrganismChange,
    organism_change,
    round_trip_refusal,
)
from strategist.domain.strategy.revision import strategy_revision
from strategist.domain.strategy.session import (
    StrategyGraph,
    StrategySession,
    strategy_root_id,
)
from strategist.domain.strategy.spec_fold import (
    fold_option_criteria,
)
from strategist.domain.strategy.spec_reconciliation import (
    spec_without_pending_analyses,
)
from strategist.domain.strategy.spec_tree import (
    build_step_tree,
)
from strategist.domain.strategy.step_words import added_searches, step_words
from strategist.domain.strategy.strategy_description import strategy_description
from strategist.domain.strategy.types import SyncStateProtocol
from strategist.services.strategies.auto_import import (
    import_gene_set_for_conversation,
)
from strategist.services.strategies.commit_tree import CommitTarget, commit_tree
from strategist.services.strategies.data_marks import read_data_marks
from strategist.services.strategies.naming import name_for_the_push
from strategist.services.strategies.spec_build import (
    build_strategy_from_spec,
    outcome_of,
)
from strategist.services.strategies.sync_state import ensure_sync_state


async def build_strategy(ctx: RunContext[LeadDeps]) -> ExecuteDelta:
    """Materialize the OperationalSpec into a real WDK strategy declaratively
    (no LLM). Requires ``frame_problem`` first. Inspect ``ledger.build`` after
    to decide ``recover_failed_steps`` or ``verify_strategy``.

    Available while the conversation holds no strategy: it would replace one that
    exists. Call ``edit_strategy`` to change a strategy, or ask the user how
    to start over."""
    deps = ctx.deps
    steps = deps.step_count
    if steps:
        raise ModelRetry(build_would_replace_the_strategy(steps))
    return await build_the_spec(deps, call_id=dispatch_call_id(ctx))


@dataclass(frozen=True)
class MintedSpec:
    """A spec that passed every check a build makes before it writes a step."""

    spec: OperationalSpec
    root: StrategyStepNode


def minted_spec(spec: OperationalSpec | None) -> MintedSpec:
    """The spec folded and minted into steps. Raises ``ModelRetry`` on a refusal."""
    if spec is None or not spec.ready_to_build:
        raise ModelRetry(build_not_ready_message(spec))
    # A criterion the structure leaves out states an option on the search a
    # step runs, so its values join that step before the tree is minted.
    folded = fold_option_criteria(spec)
    if folded.unplaced:
        raise ModelRetry(option_binds_no_step_message(folded.spec, folded.unplaced))
    trip = round_trip_refusal(folded.spec)
    if trip is not None:
        raise ModelRetry(round_trip_not_kept_message(trip))
    try:
        # A criterion waiting for its analysis has no search to mint, so the
        # EDA tools add its step once the rest is built.
        root = build_step_tree(spec_without_pending_analyses(folded.spec))
    except ValueError as exc:
        raise ModelRetry(structure_does_not_convert_message(str(exc))) from exc
    return MintedSpec(spec=folded.spec, root=root)


async def build_the_spec(deps: LeadDeps, *, call_id: str) -> ExecuteDelta:
    """Mint the thread's spec into steps and push them, with no model in between."""
    domain = deps.state.domain
    asked = asked_organisms(domain.requirements, domain.organism_picks)
    if asked:
        raise ModelRetry(organism_unnamed_message([pick.quote for _, pick in asked]))
    minted = minted_spec(domain.operational_spec)
    return await build_the_minted(deps, minted, call_id=call_id)


async def build_the_minted(
    deps: LeadDeps, minted: MintedSpec, *, call_id: str
) -> ExecuteDelta:
    """Push a minted spec as the thread's strategy.

    The thread holds no step when this runs, so the build writes the strategy
    whole.
    """
    spec = minted.spec
    agent_deps = agent_deps_for(deps, call_id=call_id)
    context = replace(agent_deps.to_strategy_context(), step_words=step_words(spec))
    current = agent_deps.strategy_session.get_graph(None)
    described = None if current is None else current.description
    comparisons = deps.state.domain.computed_comparisons
    with departures_refused():
        outcome: BuildOutcome = await build_strategy_from_spec(
            deps=context,
            root=minted.root,
            description=noted_description(described, comparisons, spec),
        )
    deps.state.domain.operational_spec = spec
    deps.state.domain.data_marks = await read_data_marks(agent_deps.site_id, [spec])
    deps.state.record_build(outcome)
    added = added_searches(spec, [c.id for c in spec.criteria])
    deps.state.turn_markers.record_added_searches(added)
    graph = agent_deps.strategy_session.get_graph(None)
    # The whole local tree is persisted even when a push fails part way, so
    # the spec is what the strategy answers to either way.
    the_strategy_now_answers_to(deps.state, spec, graph)
    if graph is not None:
        emit_chunk(
            get_stream_writer(),
            graph_snapshot_chunk(agent_deps.strategy_session, graph),
        )
    if (
        outcome.wdk_strategy_id is not None
        and graph is not None
        and agent_deps.user_id is not None
        and agent_deps.conversation_id is not None
    ):
        await import_gene_set_for_conversation(
            conversation_id=agent_deps.conversation_id,
            site_id=agent_deps.site_id,
            user_id=agent_deps.user_id,
            name=_gene_set_name(spec, graph),
        )
    return ExecuteDelta(
        outcome=outcome,
        added_searches=added,
        unsaved_gene_set=result_not_saved(
            agent_deps.site_id,
            graph,
            agent_deps.strategy_session.sync_state,
        ),
    )


_SET_NAME_LENGTH = 60


def _gene_set_name(spec: OperationalSpec, graph: StrategyGraph) -> str:
    """The name the thread's gene set takes until the thread has a title."""
    stated = (spec.interpreted_goal or spec.goal).strip().splitlines()
    if stated:
        return stated[0].strip()[:_SET_NAME_LENGTH].rstrip()
    root = graph.steps.get(graph.primary_root_id() or "")
    return graph.name if root is None else derive_strategy_name(graph.record_type, root)


async def run_recovery(
    *,
    deps: LeadDeps,
    parent_tool_call_id: str,
    reason: str,
    resume: SubAgentResume | None = None,
) -> RecoveryDelta | SubAgentApprovalWait:
    """Run recovery and re-sync the build, on a fresh dispatch or a resumed one."""
    outcome = deps.state.domain.last_build_outcome
    if outcome is None:
        msg = "No build outcome to recover from."
        raise RuntimeError(msg)
    work_order_parts = [
        f"Recovery work order: {reason}",
        f"Failed steps: {len(outcome.failed_steps)}",
        f"Skipped: {len(outcome.skipped_step_ids)}",
        f"Zero-result: {len(outcome.zero_step_ids)}",
        "Edit the affected steps via update_leaf_params / replace_subtree.",
        "Return a RecoveryDelta with actions_taken and final_outcome.",
    ]
    work_order = "\n".join(work_order_parts)
    session = deps.runtime.strategy_session
    before = _written_strategy(session)
    tree_before = live_tree(session.get_graph(None))
    agent_deps = agent_deps_for(deps, call_id=parent_tool_call_id)
    streamed = await stream_sub_agent(
        run=PhaseRun("execution", work_order),
        agent_deps=agent_deps,
        parent_tool_call_id=parent_tool_call_id,
        expected_output_type=RecoveryDelta,
        deps=deps,
        resume=resume,
    )
    if isinstance(streamed, SubAgentApprovalWait):
        return streamed
    apply_agent_state(deps, agent_deps)
    delta = streamed if streamed is not None else RecoveryDelta()
    resynced = await _resync_outcome(agent_deps, outcome)
    # Recovery writes the steps and never the spec, so the spec takes what it
    # wrote rather than reading it as the researcher's own edit next turn.
    await the_thread_wrote_the_strategy(
        deps.state,
        site_id=deps.runtime.site_id,
        graph=session.get_graph(None),
        before=tree_before,
    )
    if _written_strategy(session) == before:
        deps.state.record_resync(resynced)
    else:
        deps.state.record_build(resynced)
    return delta


async def recover_failed_steps(
    ctx: RunContext[LeadDeps],
    reason: str,
) -> RecoveryDelta:
    """Run the LLM execution-recovery sub-agent on a failed build.

    Only valid when ``ledger.build.needs_recovery`` is True and the
    failure shape is amenable to targeted edits (param replan, partial
    build). When a criterion needs a different search entirely, re-bind it
    with ``edit_strategy``, or tell the researcher which criterion needs a
    different search and end the turn.
    """
    tool_call_id = dispatch_call_id(ctx)
    result = await run_recovery(
        deps=ctx.deps,
        parent_tool_call_id=tool_call_id,
        reason=reason,
    )
    if isinstance(result, SubAgentApprovalWait):
        defer_dispatch(ctx.deps, tool_call_id, result)
    return result


@dataclass(frozen=True)
class _WrittenStrategy:
    """What the thread plans and what VEuPathDB holds of it.

    A pass that leaves both alone wrote nothing, whatever it reported.
    """

    revision: str
    wdk_step_ids: tuple[tuple[str, int], ...]


def _written_strategy(session: StrategySession) -> _WrittenStrategy:
    graph = session.get_graph(None)
    return _WrittenStrategy(
        revision="" if graph is None else strategy_revision(graph.to_strategy_ast()),
        wdk_step_ids=tuple(sorted(ensure_sync_state(session).wdk_step_ids.items())),
    )


def _records_organism(
    graph: StrategyGraph, sync_state: SyncStateProtocol
) -> OrganismChange | None:
    """The organism change of the tree recovery left, which may differ from the build's."""
    root_id = strategy_root_id(graph, sync_state)
    if root_id is None:
        return None
    return organism_change(
        rebuild_tree(root_id, graph.steps), sync_state.organism_params
    )


async def _resync_outcome(agent_deps: AgentDeps, prior: BuildOutcome) -> BuildOutcome:
    """The BuildOutcome after recovery edits, read by committing the strategy again."""
    graph = agent_deps.strategy_session.get_graph(None)
    if graph is None:
        return prior
    primary = graph.primary_root_id()
    root_id = None if primary is None else pushable_root_id(primary, graph.steps)
    if root_id is None:
        return prior
    sync_state = ensure_sync_state(agent_deps.strategy_session)
    try:
        committed = await commit_tree(
            site_id=agent_deps.site_id,
            steps=graph.steps,
            root_id=root_id,
            old=graph.to_strategy_ast(sync_state=sync_state),
            sync_state=sync_state,
            target=CommitTarget(
                name=name_for_the_push(graph, agent_deps.user_prompt),
                description=strategy_description(graph, root_id),
            ),
        )
    except VEuPathDBError, ApplyError:
        return prior
    if committed.record_type is not None:
        graph.record_type = committed.record_type
    fresh = outcome_of(
        committed,
        graph.steps,
        sync_state,
        nodes=list(graph.steps.values()),
        change=_records_organism(graph, sync_state),
    )
    fresh.pushed_step_ids = [
        *prior.pushed_step_ids,
        *(sid for sid in fresh.pushed_step_ids if sid not in prior.pushed_step_ids),
    ]
    return fresh
