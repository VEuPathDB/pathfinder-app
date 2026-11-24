"""Rebuild a stored strategy snapshot as a strategy of its own in WDK.

A snapshot names the WDK steps of the thread that produced it. Those steps
belong to that thread's strategy and keep changing with it, so a thread that
adopts a snapshot pushes the tree again and gets ids of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from assistant_core.platform.logging import get_logger
from assistant_core.platform.types import JSONObject
from veupathdb.domain.strategy import StrategyAst, walk
from veupathdb.errors import VEuPathDBError

from strategist.domain.strategy.combine_naming import name_the_combines
from strategist.domain.strategy.operations.apply import PlanDeparturesError
from strategist.domain.strategy.revision import (
    parse_strategy_ast,
    without_wdk_ids,
)
from strategist.domain.strategy.strategy_description import strategy_description
from strategist.persistence.models import PersistedStrategyGraph
from strategist.services.strategies.commit_tree import CommitTarget, commit_tree
from strategist.services.strategies.session_factory import build_strategy_session
from strategist.services.strategies.sync_state import ensure_sync_state

logger = get_logger(__name__)

__all__ = [
    "MaterializedStrategy",
    "materialize_strategy_snapshot",
    "snapshot_as_plan",
]


@dataclass(frozen=True)
class MaterializedStrategy:
    """What a thread stores after adopting a snapshot."""

    strategy_ast: JSONObject
    record_type: str | None
    step_count: int
    wdk_strategy_id: int | None
    created_wdk_strategy: bool = False
    """True when this materialization minted the WDK strategy it names."""
    is_saved: bool = False
    """The saved mark of the strategy this state names. A mint is unsaved."""


def snapshot_as_plan(
    strategy_ast: JSONObject,
    *,
    record_type: str | None = None,
    step_count: int = 0,
) -> MaterializedStrategy:
    """A snapshot the thread adopts without pushing: no WDK ids at all.

    The recorded record type and step count stand in when the stored tree no
    longer parses.
    """
    plan = without_wdk_ids(strategy_ast)
    ast = parse_strategy_ast(plan)
    if ast is None:
        return MaterializedStrategy(
            strategy_ast=plan,
            record_type=record_type,
            step_count=step_count,
            wdk_strategy_id=None,
        )
    return _plan_only(ast)


def _plan_only(ast: StrategyAst, refusal: str | None = None) -> MaterializedStrategy:
    if refusal is not None:
        ast = ast.model_copy(update={"wdk_push_errors": {ast.root.id: refusal}})
    return MaterializedStrategy(
        strategy_ast=ast.model_dump(by_alias=True, exclude_none=True, mode="json"),
        record_type=ast.record_type or None,
        step_count=_step_total(ast),
        wdk_strategy_id=None,
    )


def _step_total(ast: StrategyAst) -> int:
    total = len(walk(ast.root))
    for detached in ast.detached_roots:
        total += len(walk(detached))
    return total


async def materialize_strategy_snapshot(
    *,
    site_id: str,
    conversation_id: UUID,
    name: str,
    strategy_ast: JSONObject,
    record_type: str | None = None,
    step_count: int = 0,
) -> MaterializedStrategy:
    """Push a snapshot's tree to WDK as a new strategy.

    A snapshot that holds no tree, and a WDK push that fails, both give back
    the tree with no WDK ids: the thread owns the plan and syncs it later.
    ``record_type`` and ``step_count`` are the recorded readings that stand in
    when the stored tree no longer parses.
    """
    fresh = parse_strategy_ast(without_wdk_ids(strategy_ast))
    if fresh is None:
        return snapshot_as_plan(
            strategy_ast,
            record_type=record_type,
            step_count=step_count,
        )
    session = build_strategy_session(
        site_id=site_id,
        strategy_graph=PersistedStrategyGraph(
            id=str(conversation_id),
            name=name,
            strategy_ast=fresh,
            wdk_strategy_id=None,
        ),
    )
    graph = session.graph
    if graph is None:
        return _plan_only(fresh)
    name_the_combines(graph.steps)
    sync_state = ensure_sync_state(session)
    try:
        committed = await commit_tree(
            site_id=site_id,
            steps=graph.steps,
            root_id=fresh.root.id,
            old=None,
            sync_state=sync_state,
            target=CommitTarget(
                name=name, description=strategy_description(graph, fresh.root.id)
            ),
        )
    except PlanDeparturesError as exc:
        refusal = exc.problems.text()
        logger.warning(
            "The site cannot run the snapshot's tree; the thread keeps the plan only",
            conversation_id=str(conversation_id),
            refusal=refusal,
        )
        return _plan_only(fresh, refusal)
    except (VEuPathDBError, ValueError) as exc:
        logger.warning(
            "snapshot materialization failed; the thread keeps the plan only",
            conversation_id=str(conversation_id),
            error=str(exc),
        )
        return _plan_only(fresh)
    result = committed.sync
    if result is None:
        logger.warning(
            "WDK refused a snapshot step; the thread keeps the plan only",
            conversation_id=str(conversation_id),
            failed_step_ids=sorted(
                [*committed.drafts, *(f.step_id for f in committed.failures)]
            ),
        )
    if committed.record_type is not None:
        graph.record_type = committed.record_type
    pushed = None if result is None else graph.to_strategy_ast(sync_state=sync_state)
    if result is None or pushed is None:
        return _plan_only(fresh)
    return MaterializedStrategy(
        strategy_ast=pushed.model_dump(by_alias=True, exclude_none=True, mode="json"),
        record_type=pushed.record_type or None,
        step_count=_step_total(pushed),
        wdk_strategy_id=result.wdk_strategy_id,
        created_wdk_strategy=result.created_wdk_strategy,
    )
