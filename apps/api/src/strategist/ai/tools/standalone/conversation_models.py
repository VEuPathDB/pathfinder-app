"""Conversation tool response models."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel


class ClearStrategyResult(CamelModel):
    """Result of clearing a strategy."""

    graph_id: str
    message: str
