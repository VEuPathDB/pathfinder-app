from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import NamedTuple

from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy import StrategyAst, pushable_root_id
from veupathdb.errors import ValidationError, VEuPathDBError

from strategist.domain.refusal import Check, Problems, RefusalKey
from strategist.domain.strategy.build_outcome import StepPushFailure
from strategist.domain.strategy.combine_naming import name_the_combines
from strategist.domain.strategy.operations import (
    GraphOperation,
    ReplaceSubtreeOp,
)
from strategist.domain.strategy.operations.apply import (
    ApplyError,
    ApplyResult,
    PlanDeparturesError,
    apply_operation,
)
from strategist.domain.strategy.revision import answer_revision
from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.stated_shape import (
    SlotWrite,
    overwritten_slot,
)
from strategist.domain.strategy.strategy_description import strategy_description
from strategist.services.strategies.batch_refusal import (
    entry_state,
    refusal_after_the_batch,
)
from strategist.services.strategies.commit_tree import (
    CommitTarget,
    CommittedTree,
    commit_tree,
    drop_the_tree,
    what_the_site_cannot_run,
)
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.gene_set_refresh import defer_the_gene_set_refresh
from strategist.services.strategies.graph_rollback import (
    GraphLabels,
    graph_labels,
    restore_graph,
)
from strategist.services.strategies.live_counts import replace_counts_with_wdks
from strategist.services.strategies.naming import (
    name_for_the_push,
    name_the_thread_as_the_graph,
)
from strategist.services.strategies.organism_params import (
    tree_cross_organism_refusal,
)
from strategist.services.strategies.persist import (
    persist_strategy_ast_to_conversation,
)
from strategist.services.strategies.reconcile import (
    reconcile_sync_state_with_wdk,
)
from strategist.services.strategies.stated_sides import canonical_batch
from strategist.services.strategies.sync import SyncResult
from strategist.services.strategies.sync_state import WDKSyncState, ensure_sync_state

logger = get_logger(__name__)


@dataclass
class CommitResult:
    description: str
    dropped_step_ids: list[str] = field(default_factory=list)
    sync_result: SyncResult | None = None
    failures: list[StepPushFailure] = field(default_factory=list)
    """Steps WDK rejected, with the answer it gave. Reported, not raised.

    The edit is applied in memory and written to Postgres before the push, so
    raising made the client roll back an edit the server had kept - and the
    next read handed it straight back. The rejection is carried on the step
    (``wdk_push_error``) so all four stores say the same thing, and the calling
    tool answers with it rather than with a success line.
    """

    @property
    def failed_step_ids(self) -> list[str]:
        return [failure.step_id for failure in self.failures]


def _require_graph(deps: StrategyMutationContext) -> StrategyGraph:
    graph = deps.strategy_session.get_graph(None)
    if graph is None:
        raise ValidationError(
            title="No active strategy",
            detail="apply_and_commit requires a strategy in the session",
        )
    return graph


async def apply_and_commit(
    *,
    deps: StrategyMutationContext,
    op: GraphOperation,
) -> CommitResult:
    return await apply_operations_and_commit(deps=deps, ops=[op])


def _the_tree_the_batch_leaves(
    graph: StrategyGraph,
    old_ast: StrategyAst | None,
    sync_state: WDKSyncState,
    entry_labels: GraphLabels,
) -> StrategyAst | None:
    """The tree the applied batch leaves, or a refusal that puts the old one back.

    A batch that lands a tree no reader can rebuild takes every later read of
    the strategy with it, so the graph goes back to what it was. A tree that
    holds a loop does not fail: it never ends, so the recursion limit is one
    of the two answers this reads.
    """
    try:
        return graph.to_strategy_ast(sync_state=sync_state)
    except (ValueError, RecursionError) as exc:
        restore_graph(graph, old_ast, entry_labels)
        reason = " ".join(str(exc).split())
        msg = (
            f"the strategy this batch leaves cannot be read back, so the "
            f"operations were rolled back: {reason}"
        )
        raise ApplyError(msg) from exc


def _the_tree_wdk_is_offered(
    graph: StrategyGraph, new_ast: StrategyAst | None, sync_state: WDKSyncState
) -> StrategyAst | None:
    """The computable part of the tree, which is all WDK is offered.

    A combine that lost an input stays on the canvas and in the persisted AST,
    but WDK refuses it, so the plan is built from the surviving branch.
    """
    pushable_id = (
        pushable_root_id(new_ast.root.id, graph.steps) if new_ast is not None else None
    )
    if pushable_id is None:
        return None
    return graph.to_strategy_ast(
        pushable_id, sync_state=sync_state, include_detached=False
    )


async def _disjoint_organisms(
    deps: StrategyMutationContext, wdk_ast: StrategyAst | None
) -> Problems:
    """Why the tree the batch leaves intersects two known and disjoint
    organism scopes."""
    if wdk_ast is None:
        return Problems()
    refusal = await tree_cross_organism_refusal(deps.site_id, wdk_ast.root)
    if refusal is None:
        return Problems()
    key = RefusalKey(check=Check.THE_INTERSECT_TO_ITS_ORGANISMS)
    root = wdk_ast.root
    return Problems.one(key, refusal).under(criterion=root.id, search=root.search_name)


class _LeftTree(NamedTuple):
    full: StrategyAst | None
    offered: StrategyAst | None


async def _the_tree_without_departures(
    deps: StrategyMutationContext,
    graph: StrategyGraph,
    departures: Problems,
    sync_state: WDKSyncState,
    *,
    rollback: tuple[StrategyAst | None, GraphLabels],
) -> _LeftTree:
    old_ast, entry_labels = rollback
    try:
        full = _the_tree_the_batch_leaves(graph, old_ast, sync_state, entry_labels)
    except ApplyError as unreadable:
        key = RefusalKey(check=Check.THE_TREE_TO_ITS_READ_BACK)
        raise PlanDeparturesError(
            departures.plus(Problems.one(key, str(unreadable)))
        ) from unreadable
    offered = _the_tree_wdk_is_offered(graph, full, sync_state)
    problems = (await _disjoint_organisms(deps, offered)).plus(departures)
    if not problems.empty:
        classes = (
            Problems()
            if offered is None
            else await what_the_site_cannot_run(
                deps.site_id, graph.steps, offered.root.id
            )
        )
        restore_graph(graph, old_ast, entry_labels)
        raise PlanDeparturesError(classes.plus(problems))
    return _LeftTree(full=full, offered=offered)


def _saved_history(graph: StrategyGraph, description: str) -> int:
    held = len(graph.history)
    if graph.steps:
        graph.save_history(description)
    return held


def _replaces_a_subtree(op: GraphOperation) -> bool:
    match op:
        case ReplaceSubtreeOp():
            return True
        case _:
            return False


async def apply_operations_and_commit(
    *,
    deps: StrategyMutationContext,
    ops: Sequence[GraphOperation],
) -> CommitResult:
    """Apply every operation, then push and persist once.

    The push planner diffs the before and after trees rather than reading the
    operations, so a batch costs the same WDK round trip as a single edit.
    Either all of the operations land or none of them do.
    """
    if not ops:
        msg = "apply_operations_and_commit requires at least one operation"
        raise ValidationError(title="No operations", detail=msg)

    graph = _require_graph(deps)
    batch = await canonical_batch(
        graph=graph,
        stated=deps.stated_values,
        site_id=deps.site_id,
        ops=ops,
        validations=ensure_sync_state(deps.strategy_session).step_validations,
    )
    ops = batch.ops
    entry = entry_state(deps, graph, batch.sides)
    replaces_a_subtree = any(_replaces_a_subtree(op) for op in ops)
    sync_state = ensure_sync_state(deps.strategy_session)
    snapshot = graph.to_strategy_ast(sync_state=sync_state)
    # Deep-copy: apply_operation mutates the live nodes in-place, so a shallow
    # snapshot would alias the post-mutation state and defeat the planner's
    # change detection.
    old_ast = snapshot.model_copy(deep=True) if snapshot is not None else None
    entry_labels = graph_labels(graph)

    descriptions: list[str] = []
    dropped_step_ids: list[str] = []
    slot_writes: list[SlotWrite] = []
    try:
        for op in ops:
            write = overwritten_slot(graph, op)
            if write is not None:
                slot_writes.append(write)
            step_result = apply_operation(graph, op)
            descriptions.append(step_result.description)
            dropped_step_ids.extend(step_result.dropped_step_ids)
    except ApplyError, ValueError:
        restore_graph(graph, old_ast, entry_labels)
        raise
    renamed = bool(graph.name) and graph.name != entry_labels.name
    name_the_combines(graph.steps)
    graph.note_words(deps.step_words)

    departures = refusal_after_the_batch(
        deps=deps,
        graph=graph,
        entry=entry,
        sides=batch.sides,
        slot_writes=slot_writes,
        replaces_a_subtree=replaces_a_subtree,
    )
    new_ast, wdk_ast = await _the_tree_without_departures(
        deps, graph, departures, sync_state, rollback=(old_ast, entry_labels)
    )

    result = ApplyResult(
        description="; ".join(descriptions),
        dropped_step_ids=sorted(set(dropped_step_ids)),
    )
    history = _saved_history(graph, result.description)

    try:
        committed = await _commit_the_tree(
            deps=deps,
            graph=graph,
            old_ast=old_ast,
            wdk_ast=wdk_ast,
            sync_state=sync_state,
        )
    except VEuPathDBError, ApplyError:
        # The push raises for a step VEuPathDB already holds, so the batch is
        # rolled back rather than left ahead of the strategy it edits.
        restore_graph(graph, old_ast, entry_labels)
        del graph.history[history:]
        raise

    sync_result = None if committed is None else committed.sync
    await persist_strategy_ast_to_conversation(
        deps=deps,
        graph=graph,
        sync_result=sync_result,
    )
    if answer_revision(new_ast) != answer_revision(old_ast):
        await defer_the_gene_set_refresh(deps)
    if renamed:
        await name_the_thread_as_the_graph(deps, graph)

    return CommitResult(
        description=result.description,
        dropped_step_ids=result.dropped_step_ids,
        sync_result=sync_result,
        failures=[] if committed is None else committed.failures,
    )


async def _commit_the_tree(
    *,
    deps: StrategyMutationContext,
    graph: StrategyGraph,
    old_ast: StrategyAst | None,
    wdk_ast: StrategyAst | None,
    sync_state: WDKSyncState,
) -> CommittedTree | None:
    await reconcile_sync_state_with_wdk(
        sync_state, deps.site_id, sync_state.wdk_strategy_id
    )
    committed = None
    if wdk_ast is None or not graph.steps:
        await drop_the_tree(
            site_id=deps.site_id, steps=graph.steps, sync_state=sync_state
        )
    else:
        committed = await commit_tree(
            site_id=deps.site_id,
            steps=graph.steps,
            root_id=wdk_ast.root.id,
            old=old_ast,
            sync_state=sync_state,
            target=CommitTarget(
                name=name_for_the_push(graph, deps.user_prompt),
                description=strategy_description(graph, wdk_ast.root.id),
            ),
        )
        if committed.record_type is not None:
            graph.record_type = committed.record_type
    # VEuPathDB owns the counts. Reading them back here is what makes the
    # session, the graph snapshot and the stored strategy carry one set of
    # numbers for the tree this commit leaves behind.
    await replace_counts_with_wdks(
        graph=graph, sync_state=sync_state, site_id=deps.site_id
    )
    return committed
