from __future__ import annotations

from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.model import CamelModel


class SavedStrategyRef(CamelModel):
    """A saved strategy the user reuses as the input of a criterion.

    ``subtree`` is the saved strategy's steps, cloned with fresh ids, so the
    build pushes steps of its own instead of borrowing the saved strategy's.
    """

    conversation_id: str
    name: str
    wdk_strategy_id: int
    root_count: int | None = None
    step_count: int = 0
    subtree: StrategyStepNode

    @property
    def label(self) -> str:
        """The saved strategy named with the size it brings."""
        size = f"{self.step_count} steps"
        if self.root_count is not None:
            size = f"{self.root_count} results, {size}"
        return f"saved strategy {self.name!r} ({size})"
