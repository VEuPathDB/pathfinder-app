"""Configuration, input, and result types for parameter optimization."""

from dataclasses import dataclass
from typing import Self

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, model_validator

from pathfinder.services.experiment.types import (
    OptimizationObjective,
    ParameterType,
)


class ParameterSpec(CamelModel):
    """Describes a single parameter to optimise. Field names match WDK wire."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    param_type: ParameterType = Field(alias="type")
    min: float | None = None
    max: float | None = None
    log_scale: bool = False
    step: float | None = None
    choices: list[str] | None = None

    @model_validator(mode="after")
    def _validate_constraints(self) -> Self:
        if self.min is not None and self.max is not None and self.min >= self.max:
            msg = f"'min' ({self.min}) must be strictly less than 'max' ({self.max})"
            raise ValueError(msg)
        if self.step is not None and self.step <= 0:
            msg = f"'step' must be positive, got {self.step}"
            raise ValueError(msg)
        return self


@dataclass(slots=True)
class OptimizationConfig:
    objective: OptimizationObjective = "f1"
    beta: float = 1.0  # only for f_beta
    recall_weight: float = 1.0  # only for custom
    precision_weight: float = 1.0  # only for custom
    estimated_size_penalty: float = 0.0
    """Weight that penalises large result sets. A higher weight makes the
    optimiser prefer tighter results."""
