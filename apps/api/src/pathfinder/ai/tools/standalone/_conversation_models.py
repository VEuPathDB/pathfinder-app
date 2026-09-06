"""Conversation tool response models and helpers."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from veupathdb.domain.strategy.session import StrategyGraph, StrategySession
from veupathdb.domain.strategy.strategy_ast import StrategyAst


class RenameStrategyResult(CamelModel):
    """Result of renaming a strategy."""

    graph_id: str
    old_name: str
    new_name: str
    name: str
    record_type: str
    description: str
    plan: StrategyAst | None = None


class ClearStrategyResult(CamelModel):
    """Result of clearing a strategy."""

    graph_id: str
    message: str


def _has_strategy(graph: StrategyGraph, session: StrategySession) -> bool:
    """Check whether a graph has any strategy content."""
    sync_state = session.sync_state
    wdk_strategy_id = sync_state.wdk_strategy_id if sync_state else None
    return bool(graph.steps or wdk_strategy_id)
