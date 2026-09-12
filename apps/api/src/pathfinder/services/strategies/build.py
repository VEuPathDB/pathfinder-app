"""Strategy build service: the root step a local graph is pushed from."""

from veupathdb.domain.strategy import StrategyStep

from pathfinder.domain.strategy.session import StrategyGraph


class RootResolutionError(Exception):
    """Raised when a single root step cannot be resolved from the graph."""

    def __init__(self, message: str, root_count: int = 0) -> None:
        super().__init__(message)
        self.root_count = root_count


def resolve_root_step(
    graph: StrategyGraph,
    explicit_root_step_id: str | None,
) -> StrategyStep:
    """Resolve the root step from the graph."""

    if explicit_root_step_id:
        step = graph.get_step(explicit_root_step_id)
        if step:
            return step
        msg = f"Explicit root step '{explicit_root_step_id}' not found in graph."
        raise RootResolutionError(msg)

    # Several roots is an ordinary editing state: a search added but not yet
    # combined, or a branch just detached. The WDK strategy is the primary
    # component; the rest persist locally as detached roots and are not pushed
    # (WDK rejects a step that has inputs but no strategy).
    primary_id = graph.primary_root_id()
    if primary_id is not None:
        step = graph.get_step(primary_id)
        if step:
            return step

    msg = "No steps in graph. Create steps before building."
    raise RootResolutionError(msg)
