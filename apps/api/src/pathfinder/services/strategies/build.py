"""Strategy build service: root resolution and result count lookup."""

from dataclasses import dataclass

from pathfinder.domain.strategy.graph_model import StrategyStep
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.integrations.veupathdb.factory import get_strategy_api


@dataclass
class StepCountResult:
    """Outcome of a step count lookup."""

    step_id: int
    count: int


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


async def get_estimated_size_for_site(
    site_id: str,
    wdk_step_id: int,
    wdk_strategy_id: int | None = None,
) -> StepCountResult:
    """Get the result count for a built WDK step.

    The strategy payload carries ``estimatedSize`` and is the cheaper read; a
    direct step count query answers when it does not.

    :raises AppError: On WDK API errors.
    """
    api = get_strategy_api(site_id)
    if wdk_strategy_id is not None:
        strategy = await api.get_strategy(wdk_strategy_id)
        step = strategy.steps.get(str(wdk_step_id))
        if step is not None and step.estimated_size is not None:
            return StepCountResult(step_id=wdk_step_id, count=step.estimated_size)

    count = await api.get_step_count(wdk_step_id)
    return StepCountResult(step_id=wdk_step_id, count=count)
