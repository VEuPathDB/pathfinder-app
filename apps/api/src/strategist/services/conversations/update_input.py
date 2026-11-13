"""The PATCH payload of a thread, and the row write it becomes."""

from __future__ import annotations

from dataclasses import dataclass

from strategist.persistence.models import ConversationStrategyView
from strategist.persistence.repositories import ConversationUpdate

__all__ = ["ConversationUpdateInput", "strategy_write_of"]


@dataclass(frozen=True)
class ConversationUpdateInput:
    name: str | None
    wdk_strategy_id: int | None
    wdk_strategy_id_set: bool
    is_saved: bool | None
    is_saved_set: bool


def strategy_write_of(
    patch: ConversationUpdateInput,
    *,
    held: ConversationStrategyView,
) -> ConversationUpdate:
    """The row write one PATCH makes on a thread holding ``held``.

    An id handed in over HTTP was not minted here, so the claim goes. An id
    the row already holds is no such hand-in and leaves the claim standing.
    """
    gives_up_the_claim = (
        patch.wdk_strategy_id_set and patch.wdk_strategy_id != held.wdk_strategy_id
    )
    return ConversationUpdate(
        name=patch.name,
        wdk_strategy_id=patch.wdk_strategy_id,
        wdk_strategy_id_set=patch.wdk_strategy_id_set,
        wdk_strategy_created_here=False,
        wdk_strategy_created_here_set=gives_up_the_claim,
        is_saved=patch.is_saved,
        is_saved_set=patch.is_saved_set,
    )
