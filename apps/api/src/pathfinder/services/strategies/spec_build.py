"""Builds a strategy from a declarative step tree: replace, persist, push, sync."""

from __future__ import annotations

from typing import NamedTuple

from assistant_core.platform.logging import get_logger
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import (
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
    subtree_ids,
    wdk_search_name,
)
from veupathdb.errors import ValidationError, VEuPathDBError
from veupathdb_mcp.catalog import make_validation_callbacks, validate_parameters

from pathfinder.domain.strategy.build_outcome import (
    BuildOutcome,
    NodeResult,
    StepPushFailure,
    citable_count,
    node_status,
)
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_edit_guard import (
    contradicted_joins,
    contradicted_values,
    new_join_contradiction,
    new_value_contradiction,
)
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.persist import (
    persist_strategy_ast_to_conversation,
)
from pathfinder.services.strategies.reconcile import reconcile_sync_state_with_wdk
from pathfinder.services.strategies.stated_sides import (
    CanonicalSides,
    canonical_sides,
    canonicalize_stated_leaves,
)
from pathfinder.services.strategies.step_search import names_a_wdk_question
from pathfinder.services.strategies.step_wdk_push import push_step_to_wdk
from pathfinder.services.strategies.sync import sync_strategy_for_site
from pathfinder.services.strategies.sync_state import WDKSyncState, ensure_sync_state

logger = get_logger(__name__)


def node_results(
    nodes: list[StrategyStep],
    sync_state: WDKSyncState,
    outcome: BuildOutcome,
) -> list[NodeResult]:
    """One result per node. A node WDK refused reports the refusal, not a count.

    The WDK step a refused push leaves behind still runs the previous search,
    so its measured size answers a search the node no longer states.
    """
    failed = {f.step_id: f.error for f in outcome.failed_steps}
    return [
        NodeResult(
            node_id=node.id,
            search_name=wdk_search_name(node),
            wdk_step_id=sync_state.wdk_step_ids.get(node.id),
            count=citable_count(node.id, counts=outcome.counts, refused=failed),
            status=node_status(
                count=outcome.counts.get(node.id), failed=node.id in failed
            ),
            error=failed.get(node.id),
        )
        for node in nodes
    ]


def _replace_graph_contents(
    graph: StrategyGraph,
    root: StrategyStepNode,
    *,
    sync_state: WDKSyncState,
    name: str | None,
    description: str | None,
) -> None:
    """Replace the graph with the spec tree, and forget the counts it had.

    The old graph goes to history first, so a hand-edited parameter has a way
    back. A criterion id can name a step in both trees, so no count survives.
    """
    if graph.steps:
        graph.save_history("Replaced by the operational spec")

    sync_state.step_counts.clear()
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    graph.last_step_id = root.id
    if name is not None:
        graph.name = name
    if description is not None:
        graph.description = description


def _a_build_the_spec_refuses(
    deps: StrategyMutationContext,
    graph: StrategyGraph,
    root: StrategyStepNode,
    sides: CanonicalSides,
) -> str | None:
    """Why the tree this build would leave behind departs from the spec.

    A build writes a whole tree, so its leaves carry values and its combines
    carry operators. Both are measured here, the way the commit layer measures
    the tree a batch leaves behind.
    """
    candidate = StrategyGraph(graph.id, graph.name, graph.site_id)
    candidate.steps = flatten_tree(root)
    candidate.recompute_roots()
    join = new_join_contradiction(
        structure=deps.stated_structure,
        graph=candidate,
        criteria=deps.stated_criteria,
        before=contradicted_joins(deps.stated_structure, graph, deps.stated_criteria),
    )
    if join is not None:
        return join
    return new_value_contradiction(
        stated=sides.stated,
        graph=candidate,
        before=contradicted_values(sides.stated, graph, sides.entry),
    )


class _CanonicalBuild(NamedTuple):
    """The tree this build writes, and the sides the guard measures it against."""

    root: StrategyStepNode
    sides: CanonicalSides


async def _canonical_build(
    deps: StrategyMutationContext, graph: StrategyGraph, root: StrategyStepNode
) -> _CanonicalBuild:
    """The build in the catalog's form, and the two sides the guard reads.

    The canonicalization writes a tree of its own, so a build the spec refuses
    leaves the caller's tree as the caller wrote it. A leaf the catalog turns
    down has no canonical form, and its refusal is reported by its own push.
    """
    callbacks = make_validation_callbacks(deps.site_id)
    written = root.model_copy(deep=True)
    try:
        writes = await canonicalize_stated_leaves(
            root=written,
            stated=deps.stated_values,
            site_id=deps.site_id,
            record_type=graph.record_type or "transcript",
            callbacks=callbacks,
        )
    except ValidationError:
        written, writes = root.model_copy(deep=True), []
    sides = await canonical_sides(
        graph=graph, stated=deps.stated_values, writes=writes, callbacks=callbacks
    )
    return _CanonicalBuild(root=written, sides=sides)


async def build_strategy_from_spec(
    *,
    deps: StrategyMutationContext,
    root: StrategyStepNode,
    name: str | None = None,
    description: str | None = None,
) -> BuildOutcome:
    """Build a declarative tree into the graph, WDK, and the database.

    A per-step failure does not abort the build. Sibling subtrees still push.
    """
    session = deps.strategy_session
    graph = session.get_graph(None)
    if graph is None:
        msg = "no active strategy graph for the current conversation"
        raise RuntimeError(msg)

    built = await _canonical_build(deps, graph, root)
    root = built.root
    refusal = _a_build_the_spec_refuses(deps, graph, root, built.sides)
    if refusal is not None:
        raise ApplyError(refusal)

    steps_by_id = flatten_tree(root)
    nodes = [steps_by_id[sid] for sid in subtree_ids(root.id, steps_by_id)]
    sync_state = ensure_sync_state(session)
    _replace_graph_contents(
        graph, root, sync_state=sync_state, name=name, description=description
    )

    await reconcile_sync_state_with_wdk(
        sync_state,
        deps.site_id,
        sync_state.wdk_strategy_id,
    )

    # The local tree persists before any push, so a slow or failed push still
    # leaves the declared structure on record.
    await persist_strategy_ast_to_conversation(
        deps=deps,
        graph=graph,
        sync_result=None,
    )

    outcome = BuildOutcome()
    await _push_tree_to_wdk(
        nodes=nodes,
        graph_record_type=graph.record_type or "transcript",
        site_id=deps.site_id,
        sync_state=sync_state,
        outcome=outcome,
    )

    if outcome.failed_steps or outcome.skipped_step_ids:
        # A sync raises when a step has no WDK ID, so only the tree persists.
        await persist_strategy_ast_to_conversation(
            deps=deps,
            graph=graph,
            sync_result=None,
        )
        outcome.node_results = node_results(nodes, sync_state, outcome)
        return outcome

    try:
        sync_result = await sync_strategy_for_site(
            graph=graph,
            sync_state=sync_state,
            site_id=deps.site_id,
            strategy_name=graph.name,
        )
    except VEuPathDBError as exc:
        logger.warning("strategy sync failed", error=str(exc))
        await persist_strategy_ast_to_conversation(
            deps=deps,
            graph=graph,
            sync_result=None,
        )
        outcome.failed_steps.append(
            StepPushFailure(
                step_id=root.id,
                search_name=root.search_name,
                error=str(exc),
            ),
        )
        outcome.node_results = node_results(nodes, sync_state, outcome)
        return outcome

    outcome.wdk_strategy_id = sync_result.wdk_strategy_id
    outcome.wdk_url = sync_result.wdk_url
    outcome.counts = {str(k): v for k, v in sync_result.counts.items()}
    outcome.root_count = sync_result.root_count
    outcome.zero_step_ids = list(sync_result.zero_step_ids)

    outcome.node_results = node_results(nodes, sync_state, outcome)
    await persist_strategy_ast_to_conversation(
        deps=deps,
        graph=graph,
        sync_result=sync_result,
    )
    return outcome


async def _push_tree_to_wdk(
    *,
    nodes: list[StrategyStep],
    graph_record_type: str,
    site_id: str,
    sync_state: WDKSyncState,
    outcome: BuildOutcome,
) -> None:
    """Push every node in dependency order, and record each failure and skip.

    Parameters pass validation against the refreshed WDK spec before the push,
    so an invalid value costs no round trip.
    """
    failed_node_ids: set[str] = set()
    steps_by_id = {node.id: node for node in nodes}
    callbacks = make_validation_callbacks(site_id)
    for node in nodes:
        if _has_failed_descendant(node, failed_node_ids, steps_by_id):
            outcome.skipped_step_ids.append(node.id)
            continue
        search_name = wdk_search_name(node)
        push_parameters: dict[str, ParamValue] = dict(node.parameters)
        if names_a_wdk_question(node):
            try:
                push_parameters = (
                    await validate_parameters(
                        SearchContext(
                            site_id=site_id,
                            record_type=graph_record_type,
                            search_name=search_name,
                        ),
                        parameters=dict(node.parameters),
                        callbacks=callbacks,
                    )
                ).params
            except ValidationError as exc:
                detail = exc.detail or exc.title
                sync_state.wdk_push_errors[node.id] = detail
                failed_node_ids.add(node.id)
                outcome.failed_steps.append(
                    StepPushFailure(
                        step_id=node.id,
                        search_name=search_name,
                        error=detail,
                        wdk_status=exc.status,
                    ),
                )
                continue
        wdk_id, _validation, failure = await push_step_to_wdk(
            sync_state=sync_state,
            step=node,
            site_id=site_id,
            record_type=graph_record_type,
            search_name=search_name,
            parameters=push_parameters,
        )
        if failure is not None:
            sync_state.wdk_push_errors[node.id] = failure.error
            failed_node_ids.add(node.id)
            outcome.failed_steps.append(failure)
            continue
        if wdk_id is not None:
            sync_state.wdk_push_errors.pop(node.id, None)
            outcome.pushed_step_ids.append(node.id)


def _has_failed_descendant(
    node: StrategyStep,
    failed_ids: set[str],
    steps: dict[str, StrategyStep],
) -> bool:
    """Report whether any descendant of the node already failed its push."""
    for input_id in node.input_ids():
        if input_id in failed_ids:
            return True
        child = steps.get(input_id)
        if child is not None and _has_failed_descendant(child, failed_ids, steps):
            return True
    return False
