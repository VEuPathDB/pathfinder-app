"""The context every experiment phase receives."""

from dataclasses import dataclass

from pathfinder.services.experiment.store import ExperimentStore
from pathfinder.services.experiment.types import Experiment, ExperimentConfig


@dataclass
class PhaseContext:
    """The configuration, the experiment the phases mutate, and its store."""

    config: ExperimentConfig
    experiment: Experiment
    store: ExperimentStore
