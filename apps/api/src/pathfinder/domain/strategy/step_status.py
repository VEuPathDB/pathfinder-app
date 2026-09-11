"""The build state of one step, derived from its wiring, its WDK id and its bundle.

A stored copy would need updating at every push, parameter edit and rewire.
"""

from __future__ import annotations

from enum import StrEnum

from veupathdb.domain.strategy.graph_model import StrategyStep, is_computable
from veupathdb.domain.strategy.validation import StepValidation


class StepStatus(StrEnum):
    """The state of a step. READY means the step is complete but is not yet in WDK."""

    DRAFT = "draft"
    READY = "ready"
    BUILT = "built"
    INVALID = "invalid"

    @property
    def is_pushable(self) -> bool:
        """A draft is not ready for WDK. Every other status is pushable."""
        return self is not StepStatus.DRAFT


def step_status(
    step: StrategyStep,
    *,
    wdk_step_id: int | None,
    validation: StepValidation | None,
    has_open_params: bool,
) -> StepStatus:
    """Returns the state of a step. The status is derived on each call, never stored."""
    if has_open_params or not is_computable(step):
        return StepStatus.DRAFT
    if wdk_step_id is None:
        return StepStatus.READY
    if validation is not None and validation.rejects():
        return StepStatus.INVALID
    return StepStatus.BUILT
