"""Core type aliases and Literal types for the Experiment Lab."""

from typing import Literal

type Classification = Literal["TP", "FP", "FN", "TN"]

ExperimentMode = Literal["single", "multi-step", "import"]

ParameterType = Literal["numeric", "integer", "categorical"]

ExperimentStatus = Literal["pending", "running", "completed", "error", "cancelled"]

ExperimentProgressPhase = Literal[
    "started",
    "evaluating",
    "cross_validating",
    "enriching",
    "completed",
    "error",
]

ControlValueFormat = Literal["newline", "json_list", "comma"]

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
