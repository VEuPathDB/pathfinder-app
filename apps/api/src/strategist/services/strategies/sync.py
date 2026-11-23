"""The strategy's step tree as WDK keys it, and what a tree write answers."""

from dataclasses import dataclass

from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.errors import WDKError
from veupathdb.wdk import (
    MissingWDKStepIdError,
    WDKStepTree,
    build_wdk_step_tree,
    walk_wdk_step_tree,
)

from strategist.platform.errors import StrategyCompilationError
from strategist.services.strategies.sync_state import WDKSyncState


class TreeNotHeldError(WDKError):
    def __init__(self, written: WDKStepTree, held: WDKStepTree) -> None:
        super().__init__(
            detail=(
                f"after the write the strategy holds root step {held.step_id} over "
                f"{len(walk_wdk_step_tree(held))} steps, not the tree written, root "
                f"step {written.step_id} over {len(walk_wdk_step_tree(written))} steps"
            ),
            status=409,
        )


@dataclass
class SyncResult:
    """Outcome of a successful strategy sync."""

    wdk_strategy_id: int | None
    wdk_url: str | None
    root_step_id: int
    counts: dict[str, int | None]
    root_count: int | None
    zero_step_ids: list[str]
    step_count: int
    created_wdk_strategy: bool = False
    """True when this sync minted the WDK strategy, rather than updating one."""


def build_step_tree_from_graph(
    root: StrategyStepNode,
    wdk_step_ids: dict[str, int],
) -> WDKStepTree:
    """Build a WDK step tree, replacing local step IDs with WDK step IDs.

    :raises StrategyCompilationError: If any step in the tree lacks a WDK step ID.
    """
    try:
        return build_wdk_step_tree(root, wdk_step_ids)
    except MissingWDKStepIdError as exc:
        raise StrategyCompilationError(str(exc)) from exc


def step_tree_is_current(root_step: StrategyStepNode, sync_state: WDKSyncState) -> bool:
    """True when the WDK strategy already holds the tree this graph maps to.

    The tree is keyed by WDK step ids, so a step recreated under a new id
    moves the tree even when every local id stays the same.
    """
    if sync_state.wdk_strategy_id is None:
        return False
    try:
        step_tree = build_step_tree_from_graph(root_step, sync_state.wdk_step_ids)
    except StrategyCompilationError:
        return False
    return step_tree == sync_state.wdk_step_tree
