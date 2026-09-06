"""The experiment half of the workbench facade."""

from pathfinder.services.experiment.store import get_experiment_store
from pathfinder.services.experiment.types import Experiment


async def get_experiment(experiment_id: str) -> Experiment | None:
    """The experiment with this id, or None when the workbench holds no such id."""
    return await get_experiment_store().aget(experiment_id)
