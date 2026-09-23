"""WDK synchronization state - companion to StrategyGraph.

Holds all WDK-specific metadata that services populate during push/sync
operations. The domain layer (StrategyGraph) never touches this - it
manages graph topology only.
"""

from dataclasses import dataclass, field

from veupathdb.domain.strategy import StepValidation, StrategyAst
from veupathdb.wdk import WDKStepTree

from pathfinder.domain.strategy.session import StrategySession


@dataclass
class WDKSyncState:
    """WDK synchronization metadata for a strategy graph."""

    wdk_step_ids: dict[str, int] = field(default_factory=dict)
    step_counts: dict[str, int | None] = field(default_factory=dict)
    step_validations: dict[str, StepValidation] = field(default_factory=dict)
    wdk_strategy_id: int | None = None
    wdk_strategy_name: str | None = None
    """The name WDK holds for the strategy, as last read or written; None when unknown."""
    wdk_step_tree: WDKStepTree | None = None
    wdk_push_errors: dict[str, str] = field(default_factory=dict)
    # Snapshot of the AST as it existed at the last successful push. Lets the
    # diff planner compare new state against the actually-pushed state instead
    # of always treating every step as new.
    last_pushed_ast: StrategyAst | None = None

    @property
    def wdk_root_step_id(self) -> int | None:
        """The WDK step the pushed strategy is rooted on."""
        tree = self.wdk_step_tree
        return None if tree is None else tree.step_id


def ensure_sync_state(session: StrategySession) -> WDKSyncState:
    """Get or create the concrete WDKSyncState on a session.

    The single place in the codebase where ``isinstance(x, WDKSyncState)``
    is used.  Read-only consumers use ``SyncStateProtocol``; mutation
    sites call this function to get the concrete type.
    """
    state = session.sync_state
    if isinstance(state, WDKSyncState):
        return state
    new_state = WDKSyncState()
    session.sync_state = new_state
    return new_state
