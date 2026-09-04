"""Bootstrap robustness types for the Experiment Lab."""

from assistant_core.platform.pydantic_base import CamelModel, RoundedFloat
from pydantic import ConfigDict, Field


class ConfidenceInterval(CamelModel):
    """Bootstrap confidence interval for a single metric."""

    model_config = ConfigDict(frozen=True)

    lower: RoundedFloat = 0.0
    mean: RoundedFloat = 0.0
    upper: RoundedFloat = 0.0
    std: RoundedFloat = 0.0


class BootstrapResult(CamelModel):
    """Robustness assessment via bootstrap resampling."""

    model_config = ConfigDict(frozen=True)

    n_iterations: int = 0
    metric_cis: dict[str, ConfidenceInterval] = Field(default_factory=dict)
