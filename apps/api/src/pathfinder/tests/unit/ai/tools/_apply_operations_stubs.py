"""Graph, context and commit stubs the ``apply_operations`` tests share."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

import pytest
from pydantic_ai import RunContext
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.domain.strategy.operations import GraphOperation
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

type Commit = Callable[..., Awaitable[CommitResult]]


def leaf(step_id: str, display: str | None = None) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByTaxon",
        display_name=display,
        parameters={"organism": StringValue(value="Pf3D7")},
    )


def combine(
    step_id: str, primary: StrategyStepNode, secondary: StrategyStepNode
) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=primary,
        secondary_input=secondary,
    )


def graph_with(node: StrategyStepNode) -> StrategyGraph:
    graph = StrategyGraph(graph_id="g1", name="g", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(node))
    graph.recompute_roots()
    return graph


def revision_of(graph: StrategyGraph) -> str:
    return strategy_revision(graph.to_strategy_ast())


def context_and_commit(
    graph: StrategyGraph, committed: list[list[GraphOperation]]
) -> tuple[RunContext[AgentDeps], Commit]:
    """A run context on this graph and a commit that records what it is given."""
    session = StrategySession(site_id="plasmodb")
    session.add_graph(graph)
    session.sync_state = WDKSyncState()

    async def _commit(
        *, deps: StrategyMutationContext, ops: Sequence[GraphOperation]
    ) -> CommitResult:
        del deps
        committed.append(list(ops))
        return CommitResult(description="applied")

    return agent_run_context(strategy_session=session), _commit


def pin_apply(monkeypatch: pytest.MonkeyPatch, commit: Commit) -> None:
    monkeypatch.setattr(
        "pathfinder.ai.tools.standalone.strategy.apply_operations_and_commit",
        commit,
    )
