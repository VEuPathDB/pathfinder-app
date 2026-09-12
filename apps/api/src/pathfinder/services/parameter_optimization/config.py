"""Configuration, input, and result types for parameter optimization."""

from dataclasses import dataclass
from typing import Literal, Self

from assistant_core.platform.pydantic_base import CamelModel, RoundedFloat
from pydantic import ConfigDict, Field, model_validator
from veupathdb.domain.parameters import ParamValue
from veupathdb_mcp.controls import ControlValueFormat

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


class SweepVariantSpec(CamelModel):
    """One concrete parameter configuration in a sweep grid.

    Frozen: instances flow through the parallel fan-out path and must
    not mutate after construction. Each variant evaluates one WDK trial.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    params: dict[str, ParamValue] = Field(default_factory=dict)


VariantStatus = Literal["success", "failed"]


class SweepVariantResult(CamelModel):
    """Outcome of a single variant evaluation in a parallel sweep.

    ``status="success"`` rows have ``score`` populated and metric fields
    filled when the WDK call returned data. ``status="failed"`` rows
    populate ``error`` with the exception message and leave metrics
    ``None``. The ``best`` selection in :class:`SweepResult` ranks
    successes by ``score``.
    """

    variant_id: str
    status: VariantStatus
    params: dict[str, ParamValue] = Field(default_factory=dict)
    score: RoundedFloat | None = None
    recall: RoundedFloat | None = None
    false_positive_rate: RoundedFloat | None = None
    estimated_size: int | None = None
    positive_hits: int | None = None
    negative_hits: int | None = None
    error: str | None = None


class SweepResult(CamelModel):
    """Top-level output of a parallel parameter sweep.

    ``variants`` preserves the input order from the Cartesian grid so the
    UI lane order matches the spec. ``best`` is the highest-scoring
    success or ``None`` if every variant failed.
    """

    variants: list[SweepVariantResult]
    best: SweepVariantResult | None

    @model_validator(mode="after")
    def _select_best(self) -> Self:
        """Compute ``best`` from the successful variants if not provided."""
        if self.best is not None:
            return self
        successes = [
            v for v in self.variants if v.status == "success" and v.score is not None
        ]
        if not successes:
            return self
        self.best = max(successes, key=lambda v: v.score or float("-inf"))
        return self


@dataclass(frozen=True, slots=True)
class SweepTarget:
    """Inputs that define the WDK target search for every variant."""

    site_id: str
    record_type: str
    search_name: str
    fixed_parameters: dict[str, ParamValue]


@dataclass(frozen=True, slots=True)
class SweepControls:
    """Inputs that define the controls intersection for scoring."""

    controls_search_name: str
    controls_param_name: str
    controls_value_format: ControlValueFormat
    controls_extra_parameters: dict[str, ParamValue]
    positive_controls: list[str] | None
    negative_controls: list[str] | None
    id_field: str | None
