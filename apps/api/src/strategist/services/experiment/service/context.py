"""The context every experiment phase receives."""

from dataclasses import dataclass

from strategist.services.experiment.store import ExperimentStore
from strategist.services.experiment.types import Experiment, ExperimentConfig


@dataclass
class PhaseContext:
    """The configuration, the experiment the phases mutate, and its store."""

    config: ExperimentConfig
    experiment: Experiment
    store: ExperimentStore
