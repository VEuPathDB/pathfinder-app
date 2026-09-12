"""User-driven insert of a saved WDK strategy as a combine input.

This is the non-agent equivalent of the
``ai.tools.standalone.strategy.insert_saved_strategy`` tool. The agent
calls the tool inside an LLM turn; the HTTP endpoint calls this service
directly when the user clicks "Insert saved here..." in the strategy rail.
Both end up using the same building blocks (clone with fresh ids → push
to WDK → record consumer reference).
"""

from __future__ import annotations

from dataclasses import dataclass

from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy import (
    CombineOp,
    StepKind,
    StrategyStep,
    StrategyStepNode,
    clone_with_fresh_ids,
    flatten_tree,
    generate_step_id,
    rebuild_tree,
)
from veupathdb.errors import ValidationError, VEuPathDBError
from veupathdb.wdk import get_strategy_api
from veupathdb_mcp.wdk import (
    build_snapshot_from_wdk,
    canonicalize_synced_parameters,
)

from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import (
    ConversationUpdate,
)
from pathfinder.platform.errors import ErrorCode, NotFoundError
from pathfinder.services.strategies.commit import restore_graph
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.spec_build import (
    build_strategy_from_spec,
)
from pathfinder.services.strategies.write_lock import strategy_write_scope

logger = get_logger(__name__)


@dataclass
class InsertSavedResult:
    wdk_strategy_id: int
    inserted_saved_wdk_strategy_id: int
    inserted_saved_name: str
    # The step the insert produced: the new combine, or the inserted root when
    # the thread had no steps to combine with.
    combine_step_id: str


@dataclass(frozen=True)
class ClonedSavedStrategy:
    """A saved strategy read from WDK and cloned with fresh local step ids."""

    root: StrategyStepNode
    name: str
    record_type: str
    wdk_strategy_id: int


async def clone_saved_strategy(
    site_id: str, saved_wdk_strategy_id: int
) -> ClonedSavedStrategy:
    """Read a saved WDK strategy and clone its tree with fresh local ids.

    Every reuse of a saved strategy goes through this: WDK steps belong to one
    strategy, so a thread that reuses one pushes steps of its own.
    """
    api = get_strategy_api(site_id)
    try:
        saved = await api.get_strategy(saved_wdk_strategy_id)
    except VEuPathDBError as exc:
        raise NotFoundError(
            code=ErrorCode.STRATEGY_NOT_FOUND,
            title="saved strategy not found",
            detail=(
                f"could not load saved WDK strategy {saved_wdk_strategy_id}: {exc}"
            ),
        ) from exc
    saved_ast, wire_by_step_id = build_snapshot_from_wdk(saved)
    await canonicalize_synced_parameters(saved_ast, api, wire_by_step_id)
    return ClonedSavedStrategy(
        root=clone_with_fresh_ids(saved_ast.root),
        name=saved.name or f"Saved strategy {saved_wdk_strategy_id}",
        record_type=saved_ast.record_type,
        wdk_strategy_id=saved_wdk_strategy_id,
    )


def _build_new_root(
    *,
    graph: StrategyGraph,
    target_step_id: str,
    cloned_secondary: StrategyStepNode,
    operator: CombineOp,
    expanded_strategy_id: int,
    expanded_name: str,
) -> tuple[StrategyStepNode, str]:
    """Wrap ``target_step_id`` in a new combine that takes the saved subtree.

    Splicing is a single slot assignment now that steps reference each other
    by id. Under the nested model every ancestor had to be rebuilt on the way
    up, because changing a child meant constructing a new parent to hold it.
    """
    graph.steps.update(flatten_tree(cloned_secondary))
    # The parent is read before the combine joins the graph, because the
    # combine consumes the target step and would answer as its own parent.
    parent_info = graph.parent_of(target_step_id)
    combine = StrategyStep(
        id=generate_step_id(),
        kind=StepKind.COMBINE,
        operator=operator,
        primary_input_id=target_step_id,
        secondary_input_id=cloned_secondary.id,
        expanded_strategy_id=expanded_strategy_id,
        expanded_name=expanded_name,
    )
    graph.steps[combine.id] = combine

    if parent_info is not None:
        parent, slot = parent_info
        if slot == "primary":
            parent.primary_input_id = combine.id
        else:
            parent.secondary_input_id = combine.id
    graph.recompute_roots()

    root_id = graph.primary_root_id() or combine.id
    return rebuild_tree(root_id, graph.steps), combine.id


async def insert_saved_into_conversation(
    *,
    deps: StrategyMutationContext,
    target_step_id: str,
    saved_wdk_strategy_id: int,
    operator: CombineOp,
) -> InsertSavedResult:
    """Materialize an inserted saved strategy and push to WDK.

    This drives the same path as the agent tool: load the saved WDK
    strategy, deep-clone its tree with fresh local ids, wrap the target
    step in a new combine carrying ``expanded_*`` fields, then build via
    ``build_strategy_from_spec`` so per-step pushes are retryable.
    """
    graph = deps.strategy_session.get_graph(None)
    if graph is None:
        raise ValidationError(
            title="no active strategy",
            detail="cannot insert into a conversation with no active graph",
        )
    if target_step_id and target_step_id not in graph.steps:
        raise NotFoundError(
            code=ErrorCode.STEP_NOT_FOUND,
            title="step not found",
            detail=(
                f"step {target_step_id!r} not in active graph "
                f"(available: {sorted(graph.steps)[:20]})"
            ),
        )
    if not target_step_id and graph.steps:
        raise ValidationError(
            title="target step required",
            detail=(
                "this strategy already has steps; name the step the saved "
                "strategy combines with"
            ),
        )

    entry_ast = graph.to_strategy_ast()
    cloned = await clone_saved_strategy(deps.site_id, saved_wdk_strategy_id)
    if target_step_id:
        new_full_root, combine_step_id = _build_new_root(
            graph=graph,
            target_step_id=target_step_id,
            cloned_secondary=cloned.root,
            operator=operator,
            expanded_strategy_id=saved_wdk_strategy_id,
            expanded_name=cloned.name,
        )
    else:
        # A thread with no steps adopts the saved strategy as its own root:
        # there is no step to combine with, so nothing is collapsed.
        graph.record_type = cloned.record_type
        new_full_root, combine_step_id = cloned.root, cloned.root.id

    saved_label = cloned.name
    try:
        outcome = await build_strategy_from_spec(
            deps=deps,
            root=new_full_root,
            name=graph.name,
            description=graph.description,
        )
    except ApplyError:
        # The splice wires its combine into the graph before the build reads
        # the tree, so a refused build puts the graph back.
        restore_graph(graph, entry_ast)
        raise
    if outcome.failed_steps:
        first = outcome.failed_steps[0]
        raise ValidationError(
            title="insert pushed partial state",
            detail=(
                f"failed to push step {first.step_id!r} "
                f"({first.search_name}): {first.error}"
            ),
        )

    await _record_consumer(deps=deps, wdk_strategy_id=saved_wdk_strategy_id)

    return InsertSavedResult(
        wdk_strategy_id=outcome.wdk_strategy_id or 0,
        inserted_saved_wdk_strategy_id=saved_wdk_strategy_id,
        inserted_saved_name=saved_label,
        combine_step_id=combine_step_id,
    )


async def _record_consumer(
    *,
    deps: StrategyMutationContext,
    wdk_strategy_id: int,
) -> None:
    """Add the saved strategy to the thread's consumer list.

    This write shares the transaction that owns the thread's strategy, so it
    never waits on a row the caller's own transaction holds.
    """
    scope = strategy_write_scope(deps)
    if scope is None or deps.conversation_id is None:
        return
    async with scope as db:
        repo = ConversationRepository(db)
        conv = await repo.get_by_id(deps.conversation_id)
        if conv is None:
            return
        strategy = await repo.get_strategy(deps.conversation_id)
        existing = list(strategy.imported_saved_strategy_ids)
        if wdk_strategy_id in existing:
            return
        existing.append(wdk_strategy_id)
        await repo.update_conversation(
            conv.id,
            ConversationUpdate(imported_saved_strategy_ids=existing),
        )
