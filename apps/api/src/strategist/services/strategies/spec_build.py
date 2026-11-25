"""Builds a strategy from a declarative step tree: replace, persist, push, sync."""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

from veupathdb.domain.strategy import (
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
    subtree_ids,
    wdk_search_name,
)
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import make_validation_callbacks

from strategist.domain.refusal import Problems
from strategist.domain.strategy.build_outcome import (
    BuildOutcome,
    NodeResult,
    StepPushFailure,
    built_counts,
    node_status,
)
from strategist.domain.strategy.combine_naming import name_the_combines
from strategist.domain.strategy.operations.apply import PlanDeparturesError
from strategist.domain.strategy.orthology import OrganismChange, organism_change
from strategist.domain.strategy.revision import answer_revision
from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.spec_edit_guard import (
    contradicted_joins,
    contradicted_values,
    new_join_contradictions,
    new_value_contradictions,
)
from strategist.domain.strategy.step_words import StepWords
from strategist.domain.strategy.strategy_description import strategy_description
from strategist.services.eda.analysis_kinds import read_the_unread_kinds
from strategist.services.strategies.commit_tree import (
    CommitTarget,
    CommittedTree,
    commit_tree,
)
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.gene_set_refresh import defer_the_gene_set_refresh
from strategist.services.strategies.graph_rollback import (
    GraphLabels,
    graph_labels,
    restore_graph,
)
from strategist.services.strategies.naming import name_for_the_push
from strategist.services.strategies.organism_params import tree_organism_parameters
from strategist.services.strategies.persist import (
    persist_strategy_ast_to_conversation,
)
from strategist.services.strategies.record_classes import what_the_site_cannot_run
from strategist.services.strategies.stated_sides import (
    CanonicalSides,
    canonical_sides,
    canonicalize_stated_leaves,
)
from strategist.services.strategies.sync_state import WDKSyncState, ensure_sync_state


def outcome_of(
    committed: CommittedTree,
    steps: Mapping[str, StrategyStep],
    sync_state: WDKSyncState,
    *,
    nodes: list[StrategyStep],
    change: OrganismChange | None,
) -> BuildOutcome:
    drafts = [
        StepPushFailure(
            step_id=step_id, search_name=wdk_search_name(steps[step_id]), error=text
        )
        for step_id, text in committed.drafts.items()
    ]
    outcome = BuildOutcome(
        pushed_step_ids=list(committed.pushed),
        failed_steps=[*committed.failures, *drafts],
        skipped_step_ids=list(committed.skipped),
        wdk_strategy_id=_the_strategy_put(committed, sync_state),
        zero_step_ids=sorted(
            sid
            for sid, count in sync_state.step_counts.items()
            if committed.put and count == 0
        ),
        organism_change=change,
        not_read=sync_state.strategy_not_read,
    )
    outcome.node_results = node_results(nodes, sync_state, outcome)
    return outcome


def _the_strategy_put(committed: CommittedTree, sync_state: WDKSyncState) -> int | None:
    if committed.sync is not None:
        return committed.sync.wdk_strategy_id
    return sync_state.wdk_strategy_id if committed.put else None


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
) -> Problems:
    """Every way the tree this build would leave behind departs from the spec.

    A build writes a whole tree, so its leaves carry values and its combines
    carry operators. Both are measured here, the way the commit layer measures
    the tree a batch leaves behind.
    """
    candidate = StrategyGraph(graph.id, graph.name, graph.site_id)
    candidate.steps = flatten_tree(root)
    candidate.recompute_roots()
    joins = new_join_contradictions(
        structure=deps.stated_structure,
        graph=candidate,
        criteria=deps.stated_criteria,
        before=contradicted_joins(deps.stated_structure, graph, deps.stated_criteria),
    )
    return joins.plus(
        new_value_contradictions(
            stated=sides.stated,
            graph=candidate,
            before=contradicted_values(sides.stated, graph, sides.entry),
            after=sides.written,
        )
    )


class _Entry(NamedTuple):
    labels: GraphLabels
    history: int
    counts: dict[str, int | None]


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

    built = await _canonical_build(deps, graph, root)
    root = built.root
    problems = _a_build_the_spec_refuses(deps, graph, root, built.sides)
    if not problems.empty:
        steps = flatten_tree(root)
        classes = await what_the_site_cannot_run(deps.site_id, steps, root.id)
        raise PlanDeparturesError(classes.plus(problems))

    sync_state = ensure_sync_state(session)
    before = graph.to_strategy_ast(sync_state=sync_state)
    old = None if before is None else before.model_copy(deep=True)
    entry = _Entry(
        graph_labels(graph), len(graph.history), dict(sync_state.step_counts)
    )
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

    # The local tree persists before any push, so a slow or failed push still
    # leaves the declared structure on record.
    await persist_strategy_ast_to_conversation(
        deps=deps,
        graph=graph,
        sync_result=None,
    )

    marks = await tree_organism_parameters(deps.site_id, root)
    try:
        committed = await commit_tree(
            site_id=deps.site_id,
            steps=graph.steps,
            root_id=root.id,
            old=old,
            sync_state=sync_state,
            target=CommitTarget(
                name=name_for_the_push(graph, deps.user_prompt),
                description=strategy_description(graph, root.id),
            ),
        )
    except PlanDeparturesError:
        restore_graph(graph, old, entry.labels)
        del graph.history[entry.history :]
        sync_state.step_counts = entry.counts
        await persist_strategy_ast_to_conversation(
            deps=deps, graph=graph, sync_result=None
        )
        raise
    if committed.not_read:
        restore_graph(graph, old, entry.labels)
        del graph.history[entry.history :]
        sync_state.step_counts = entry.counts
    if committed.record_type is not None:
        graph.record_type = committed.record_type
    outcome = outcome_of(
        committed,
        graph.steps,
        sync_state,
        nodes=nodes,
        change=organism_change(root, marks),
    )
    await persist_strategy_ast_to_conversation(
        deps=deps,
        graph=graph,
        sync_result=committed.sync,
    )
    after = graph.to_strategy_ast(sync_state=sync_state)
    if (
        committed.put
        and not committed.failures
        and answer_revision(after) != answer_revision(before)
    ):
        await defer_the_gene_set_refresh(deps)
    return outcome
