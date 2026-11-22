"""Builds a strategy from a declarative step tree: replace, persist, push, sync."""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import (
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
    subtree_ids,
    wdk_search_name,
)
from veupathdb.errors import ValidationError
from veupathdb.wdk import get_strategy_api
from veupathdb_mcp.catalog import make_validation_callbacks, validate_parameters

from strategist.domain.strategy.build_outcome import (
    BuildOutcome,
    NodeResult,
    StepPushFailure,
    built_counts,
    node_status,
)
from strategist.domain.strategy.combine_naming import name_the_combines
from strategist.domain.strategy.operations.apply import ApplyError
from strategist.domain.strategy.orthology import organism_change
from strategist.domain.strategy.record_class_check import step_class_of
from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.spec_edit_guard import (
    contradicted_joins,
    contradicted_values,
    new_join_contradiction,
    new_value_contradiction,
)
from strategist.domain.strategy.step_words import StepWords
from strategist.domain.strategy.strategy_description import strategy_description
from strategist.services.eda.analysis_kinds import read_the_unread_kinds
from strategist.services.strategies._wdk_step_calls import pushed_step
from strategist.services.strategies.commit_tree import CommitTarget, commit_tree
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.gene_set_refresh import defer_the_gene_set_refresh
from strategist.services.strategies.naming import name_for_the_push
from strategist.services.strategies.organism_params import tree_organism_parameters
from strategist.services.strategies.persist import (
    persist_strategy_ast_to_conversation,
)
from strategist.services.strategies.reconcile import reconcile_sync_state_with_wdk
from strategist.services.strategies.record_classes import (
    fill_record_classes,
    tree_record_class_refusal,
    unclassed_step_failure,
)
from strategist.services.strategies.stated_sides import (
    CanonicalSides,
    canonical_sides,
    canonicalize_stated_leaves,
    unmoved,
)
from strategist.services.strategies.step_search import names_a_wdk_question
from strategist.services.strategies.sync_state import WDKSyncState, ensure_sync_state


def node_results(
    nodes: list[StrategyStep],
    sync_state: WDKSyncState,
    outcome: BuildOutcome,
) -> list[NodeResult]:
    """One result per node, its status read at the counts the sync state holds."""
    failed = {f.step_id: f.error for f in outcome.failed_steps}
    counts = built_counts(None, sync_state)
    return [
        NodeResult(
            node_id=node.id,
            search_name=wdk_search_name(node),
            wdk_step_id=sync_state.wdk_step_ids.get(node.id),
            status=node_status(count=counts.of(node.id), failed=node.id in failed),
            error=failed.get(node.id),
        )
        for node in nodes
    ]


def _replace_graph_contents(
    graph: StrategyGraph,
    root: StrategyStepNode,
    *,
    sync_state: WDKSyncState,
    description: str | None,
    step_words: StepWords,
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
    graph.note_words(step_words)
    name_the_combines(graph.steps)
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
        after=sides.written,
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
            graph=graph,
            root=written,
            stated=deps.stated_values,
            site_id=deps.site_id,
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
    description: str | None = None,
) -> BuildOutcome:
    """Build a declarative tree into the graph, WDK, and the database.

    A per-step failure does not abort the build. Sibling subtrees still push.
    The strategy keeps the thread's name.
    """
    session = deps.strategy_session
    graph = session.get_graph(None)
    if graph is None:
        msg = "no active strategy graph for the current conversation"
        raise RuntimeError(msg)

    refusal = await tree_record_class_refusal(deps.site_id, root, {})
    if refusal is not None:
        raise ApplyError(refusal)
    built = await _canonical_build(deps, graph, root)
    root = built.root
    refusal = _a_build_the_spec_refuses(deps, graph, root, built.sides)
    if refusal is not None:
        raise ApplyError(refusal)

    sync_state = ensure_sync_state(session)
    held = {step_id: dict(step.parameters) for step_id, step in graph.steps.items()}
    _replace_graph_contents(
        graph,
        root,
        sync_state=sync_state,
        description=description,
        step_words=deps.step_words,
    )
    nodes = [graph.steps[sid] for sid in subtree_ids(root.id, graph.steps)]
    # A step the build minted under a new id carries no kind yet, so the
    # catalog says which plugin reads its analysis document.
    await read_the_unread_kinds(site_id=deps.site_id, graph=graph)

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

    marks = await tree_organism_parameters(deps.site_id, root)
    outcome = BuildOutcome(organism_change=organism_change(root, marks))
    await _push_tree_to_wdk(
        nodes=nodes,
        held=held,
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

    committed = await commit_tree(
        site_id=deps.site_id,
        steps=graph.steps,
        root_id=root.id,
        old=graph.to_strategy_ast(sync_state=sync_state),
        sync_state=sync_state,
        target=CommitTarget(
            name=name_for_the_push(graph, deps.user_prompt),
            description=strategy_description(graph, root.id),
        ),
    )
    if committed.record_type is not None:
        graph.record_type = committed.record_type
    sync_result = committed.sync
    if committed.failures or sync_result is None:
        await persist_strategy_ast_to_conversation(
            deps=deps,
            graph=graph,
            sync_result=None,
        )
        outcome.failed_steps.extend(committed.failures)
        outcome.node_results = node_results(nodes, sync_state, outcome)
        return outcome

    outcome.wdk_strategy_id = sync_result.wdk_strategy_id
    outcome.zero_step_ids = list(sync_result.zero_step_ids)

    outcome.node_results = node_results(nodes, sync_state, outcome)
    await persist_strategy_ast_to_conversation(
        deps=deps,
        graph=graph,
        sync_result=sync_result,
    )
    await defer_the_gene_set_refresh(deps)
    return outcome


async def _push_tree_to_wdk(
    *,
    nodes: list[StrategyStep],
    held: Mapping[str, Mapping[str, ParamValue]],
    site_id: str,
    sync_state: WDKSyncState,
    outcome: BuildOutcome,
) -> None:
    """Push every node in dependency order, and record each failure and skip.

    A value the build states passes validation before the push, so an invalid
    one costs no round trip; a value the step already held goes as it is.
    """
    failed_node_ids: set[str] = set()
    steps_by_id = {node.id: node for node in nodes}
    await fill_record_classes(site_id, steps_by_id)
    callbacks = make_validation_callbacks(site_id)
    for node in nodes:
        if _has_failed_descendant(node, failed_node_ids, steps_by_id):
            outcome.skipped_step_ids.append(node.id)
            continue
        search_name = wdk_search_name(node)
        record_type = step_class_of(steps_by_id, node.id)
        if record_type is None:
            unclassed = unclassed_step_failure(node.id, search_name)
            sync_state.wdk_push_errors[node.id] = unclassed.error
            failed_node_ids.add(node.id)
            outcome.failed_steps.append(unclassed)
            continue
        push_parameters: dict[str, ParamValue] = dict(node.parameters)
        context = unmoved(node.parameters, held.get(node.id, {}))
        if names_a_wdk_question(node):
            try:
                validated = await validate_parameters(
                    SearchContext(
                        site_id=site_id,
                        record_type=record_type,
                        search_name=search_name,
                    ),
                    stated={
                        name: value
                        for name, value in node.parameters.items()
                        if name not in context
                    },
                    context=context,
                    held_validation=sync_state.step_validations.get(node.id),
                    callbacks=callbacks,
                    about=None,
                )
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
            push_parameters = {**node.parameters, **context, **validated.params}
            if validated.record_class:
                node.record_class = validated.record_class
                record_type = validated.record_class
        failure = await pushed_step(
            get_strategy_api(site_id), sync_state, node, record_type, push_parameters
        )
        if failure is not None:
            sync_state.wdk_push_errors[node.id] = failure.error
            failed_node_ids.add(node.id)
            outcome.failed_steps.append(failure)
            continue
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
