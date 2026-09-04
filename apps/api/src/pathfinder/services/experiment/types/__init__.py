"""Shared data types for the Experiment Lab.

This package consolidates all experiment-related dataclasses, type aliases,
and serialization helpers. All public symbols are re-exported here.
"""

from pathfinder.services.enrichment.types import (
    EnrichmentAnalysisType,
    EnrichmentResult,
    EnrichmentTerm,
)
from pathfinder.services.experiment.types.control_result import (
    ControlSetData,
    ControlTargetData,
    ControlTestResult,
)
from pathfinder.services.experiment.types.core import (
    ControlValueFormat,
    ExperimentMode,
    ExperimentProgressPhase,
    ExperimentStatus,
    OptimizationObjective,
    ParameterType,
)
from pathfinder.services.experiment.types.experiment import (
    BatchExperimentConfig,
    BatchOrganismTarget,
    Experiment,
    ExperimentConfig,
)
from pathfinder.services.experiment.types.metrics import (
    ConfusionMatrix,
    CrossValidationResult,
    ExperimentMetrics,
    FoldMetrics,
    GeneInfo,
)
from pathfinder.services.experiment.types.robustness import (
    BootstrapResult,
    ConfidenceInterval,
)
from pathfinder.services.experiment.types.serialization import experiment_to_json

__all__ = [
    # Experiment
    "BatchExperimentConfig",
    "BatchOrganismTarget",
    # Robustness
    "BootstrapResult",
    "ConfidenceInterval",
    # Metrics
    "ConfusionMatrix",
    # Control result
    "ControlSetData",
    "ControlTargetData",
    "ControlTestResult",
    "ControlValueFormat",
    "CrossValidationResult",
    "EnrichmentAnalysisType",
    # Enrichment
    "EnrichmentResult",
    "EnrichmentTerm",
    "Experiment",
    "ExperimentConfig",
    "ExperimentMetrics",
    "ExperimentMode",
    "ExperimentProgressPhase",
    "ExperimentStatus",
    "FoldMetrics",
    "GeneInfo",
    "OptimizationObjective",
    "ParameterType",
    # Serialization
    "experiment_to_json",
]
