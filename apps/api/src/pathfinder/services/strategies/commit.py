from collections.abc import Sequence
from dataclasses import dataclass, field

from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy import (
    StrategyAst,
    pushable_root_id,
    subtree_ids,
    wdk_search_name,
)
from veupathdb.errors import ValidationError, VEuPathDBError
from veupathdb.wdk import get_strategy_api

from pathfinder.domain.strategy.build_outcome import StepPushFailure
from pathfinder.domain.strategy.operations import (
    GraphOperation,
    ReplaceStrategyOp,
)
from pathfinder.domain.strategy.operations.apply import (
    ApplyError,
    ApplyResult,
    apply_operation,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.stated_shape import (
    SlotWrite,
    criteria_with_steps,
    evicted_by,
    overwritten_slot,
    stated_shape,
)
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.persist import (
    persist_strategy_ast_to_conversation,
)
from pathfinder.services.strategies.reconcile import (
    reconcile_sync_state_with_wdk,
)
from pathfinder.services.strategies.step_push_planner import plan_step_pushes
from pathfinder.services.strategies.step_wdk_push import push_steps_with_plan
from pathfinder.services.strategies.sync import (
    SyncResult,
    step_tree_is_current,
    sync_strategy_for_site,
)
from pathfinder.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from pathfinder.services.strategies.wdk_counts import invalidate_counts_for

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
            title="No active strategy graph",
            detail="apply_and_commit requires an initialized graph in the session",
        )
    return graph


async def apply_and_commit(
    *,
    deps: StrategyMutationContext,
    op: GraphOperation,
) -> CommitResult:
    return await apply_operations_and_commit(deps=deps, ops=[op])


def _restore_graph(graph: StrategyGraph, old_ast: StrategyAst | None) -> None:
    """Put the graph back the way it was before a failed batch.

    ``apply_operation`` edits the live nodes, so a batch that fails partway
    has already changed the graph. Replaying the pre-batch tree is what makes
    a rejected batch a no-op rather than a half-applied edit.
    """
    graph.steps.clear()
    graph.roots.clear()
    graph.last_step_id = None
    if old_ast is None:
        return
    apply_operation(graph, ReplaceStrategyOp(root=old_ast.root))


def _replaces_a_subtree(op: GraphOperation) -> bool:
    match op.kind:
        case "replaceSubtree":
            return True
        case _:
            return False


def _departure_from_the_spec(
    *,
    graph: StrategyGraph,
    stated: frozenset[str],
    outside: set[str],
) -> str | None:
    """How the graph departs from the criteria the spec states, or nothing."""
    shape = stated_shape(
        graph=graph,
        root_id=graph.primary_root_id() or "",
        criteria=stated,
        outside=outside,
    )
    if shape.holds:
        return None
    return (
        f"a replaced subtree would leave the strategy holding "
        f"{list(shape.searches)} where the spec states {list(shape.stated)}"
    )


def _eviction_message(write: SlotWrite, *, stated: frozenset[str]) -> str:
    """Why a slot write is refused, naming the step it would take off the tree."""
    answers = (
        " and answers a criterion the spec states"
        if write.occupant_step_id in stated
        else ""
    )
    return (
        f"the {write.slot} input of {write.target_step_id} holds "
        f"{write.occupant_step_id}{answers}, and this batch overwrites it, so "
        f"{write.occupant_step_id} would leave the strategy without being "
        f"deleted. Delete that step first, or keep it wired into the tree"
    )


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
    entry_step_ids = set(graph.steps)
    entry_reachable = set(subtree_ids(graph.primary_root_id() or "", graph.steps))
    replaces_a_subtree = any(_replaces_a_subtree(op) for op in ops)
    sync_state = ensure_sync_state(deps.strategy_session)
    snapshot = graph.to_strategy_ast(sync_state=sync_state)
    # Deep-copy: apply_operation mutates the live nodes in-place, so a shallow
    # snapshot would alias the post-mutation state and defeat plan_step_pushes
    # change detection.
    old_ast = snapshot.model_copy(deep=True) if snapshot is not None else None

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
        _restore_graph(graph, old_ast)
        raise

    # The spec addresses this graph by step id, so a criterion answers to a
    # step the graph held before the batch or to one the batch mints.
    stated = criteria_with_steps(
        deps.stated_criteria,
        entry_step_ids,
        minted=set(graph.steps) - entry_step_ids,
    )
    eviction = evicted_by(graph, slot_writes, was_reachable=entry_reachable)
    if eviction is not None:
        _restore_graph(graph, old_ast)
        raise ApplyError(_eviction_message(eviction, stated=stated))

    if replaces_a_subtree and stated:
        departure = _departure_from_the_spec(
            graph=graph, stated=stated, outside=entry_step_ids - entry_reachable
        )
        if departure is not None:
            _restore_graph(graph, old_ast)
            raise ApplyError(departure)

    result = ApplyResult(
        description="; ".join(descriptions),
        dropped_step_ids=sorted(set(dropped_step_ids)),
    )
    if graph.steps:
        graph.save_history(result.description)

    new_ast = graph.to_strategy_ast(sync_state=sync_state)
    # WDK is only offered the computable part of the graph. A combine that
    # lost an input stays on the canvas and in the persisted AST, but pushing
    # it would be rejected, so the plan is built from the surviving branch.
    pushable_id = (
        pushable_root_id(new_ast.root.id, graph.steps) if new_ast is not None else None
    )
    wdk_ast = (
        graph.to_strategy_ast(
            pushable_id, sync_state=sync_state, include_detached=False
        )
        if pushable_id is not None
        else None
    )

    sync_result = await _commit_to_wdk(
        deps=deps,
        graph=graph,
        old_ast=old_ast,
        new_ast=wdk_ast,
        dropped_step_ids=result.dropped_step_ids,
    )

    await persist_strategy_ast_to_conversation(
        deps=deps,
        graph=graph,
        sync_result=sync_result.sync_result,
    )

    return CommitResult(
        description=result.description,
        dropped_step_ids=result.dropped_step_ids,
        sync_result=sync_result.sync_result,
        failures=sync_result.failures,
    )


@dataclass
class _WDKCommitOutcome:
    succeeded_step_ids: list[str]
    failures: list[StepPushFailure]
    sync_result: SyncResult | None


_DETACHED = "the WDK strategy does not hold this step, so it computes nothing"


def _detached_failures(
    graph: StrategyGraph,
    sync_state: WDKSyncState,
    sync_result: SyncResult,
) -> list[StepPushFailure]:
    """A step the strategy leaves out of its tree is a failed push.

    The step exists in the account and answers no count, so reporting it as
    pushed would put a number on the edit that WDK never computed. The record
    names the last put, so a put that lists the step again ends it.
    """
    for step_id in sync_result.counts:
        if sync_state.wdk_push_errors.get(step_id) == _DETACHED:
            sync_state.wdk_push_errors.pop(step_id)
    failures: list[StepPushFailure] = []
    for step_id in sync_result.detached_step_ids:
        step = graph.steps.get(step_id)
        if step is None:
            continue
        sync_state.wdk_push_errors[step_id] = _DETACHED
        failures.append(
            StepPushFailure(
                step_id=step_id,
                search_name=wdk_search_name(step),
                error=_DETACHED,
            )
        )
    return failures


async def _put_the_step_tree(
    *,
    deps: StrategyMutationContext,
    graph: StrategyGraph,
    sync_state: WDKSyncState,
    new_ast: StrategyAst | None,
) -> SyncResult | None:
    """Re-root the WDK strategy on the tree the graph now maps to.

    A recreated step keeps its local id under a new WDK id, so the local shape
    alone does not say whether the tree moved.
    """
    if (
        new_ast is None
        or not graph.steps
        or step_tree_is_current(new_ast.root, sync_state)
    ):
        return None
    try:
        return await sync_strategy_for_site(
            graph=graph,
            sync_state=sync_state,
            site_id=deps.site_id,
            strategy_name=graph.name,
        )
    except VEuPathDBError as exc:
        logger.warning(
            "sync_strategy_for_site failed; persisting partial state",
            error=str(exc),
        )
        return None


async def _commit_to_wdk(
    *,
    deps: StrategyMutationContext,
    graph: StrategyGraph,
    old_ast: StrategyAst | None,
    new_ast: StrategyAst | None,
    dropped_step_ids: list[str],
) -> _WDKCommitOutcome:
    sync_state = ensure_sync_state(deps.strategy_session)
    api = get_strategy_api(deps.site_id)

    await reconcile_sync_state_with_wdk(
        sync_state,
        deps.site_id,
        sync_state.wdk_strategy_id,
    )

    succeeded: list[str] = []
    failures: list[StepPushFailure] = []
    recreated: dict[str, int] = {}
    if new_ast is not None:
        plan = plan_step_pushes(
            old_ast=old_ast,
            new_ast=new_ast,
            existing_wdk_ids=sync_state.wdk_step_ids,
        )
        push_outcome = await push_steps_with_plan(graph, sync_state, deps.site_id, plan)
        succeeded = push_outcome.succeeded
        failures = push_outcome.failures
        recreated = push_outcome.recreated_wdk_ids
        # A pushed step's parameters just changed, so its stored count now
        # describes the OLD step. A refused step is in the same position: WDK
        # kept the previous search. Mark both unknown rather than let a stale
        # number be read back as current fact.
        invalidate_counts_for(
            sync_state, [*succeeded, *(failure.step_id for failure in failures)]
        )

    # The id mapping is kept until WDK confirms the delete. The strategy push
    # below is what orphans these steps, so deleting them first is refused.
    orphaned: dict[str, int] = {}
    for sid in dropped_step_ids:
        sync_state.step_counts.pop(sid, None)
        sync_state.step_validations.pop(sid, None)
        sync_state.wdk_push_errors.pop(sid, None)
        wdk_id = sync_state.wdk_step_ids.get(sid)
        if wdk_id is not None:
            orphaned[sid] = wdk_id

    sync_result = (
        None
        if failures
        else await _put_the_step_tree(
            deps=deps, graph=graph, sync_state=sync_state, new_ast=new_ast
        )
    )
    if sync_result is not None:
        failures.extend(_detached_failures(graph, sync_state, sync_result))

    # A step the put replaced belongs to no strategy either. Its local id now
    # names the new WDK step, so there is no mapping to forget for it, and a
    # put that did not land leaves it on the tree.
    replaced = list(recreated.values()) if sync_result is not None else []
    if orphaned or replaced:
        leftover = set(await api.delete_orphaned_steps([*orphaned.values(), *replaced]))
        for sid, wdk_id in orphaned.items():
            if wdk_id not in leftover:
                sync_state.wdk_step_ids.pop(sid, None)
        if leftover:
            logger.warning(
                "Some orphaned WDK steps could not be deleted",
                step_ids=sorted(leftover),
            )

    return _WDKCommitOutcome(
        succeeded_step_ids=succeeded,
        failures=failures,
        sync_result=sync_result,
    )
