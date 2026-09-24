"""Core type aliases and Literal types for experiment runs."""

from typing import Literal

ParameterType = Literal["numeric", "integer", "categorical"]

ExperimentStatus = Literal["pending", "running", "completed", "error", "cancelled"]

OptimizationObjective = Literal[
    "f1",
    "f_beta",
    "recall",
    "precision",
    "specificity",
    "balanced_accuracy",
    "mcc",
    "youdens_j",
    "custom",
]
