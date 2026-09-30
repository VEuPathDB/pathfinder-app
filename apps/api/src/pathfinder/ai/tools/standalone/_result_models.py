"""The step-result tools' own result shape, and the input each one refuses."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from pydantic_ai.exceptions import ModelRetry

from pathfinder.domain.evidence import ColumnFit


class EstimatedSizeResult(CamelModel):
    """Result of a step size estimation."""

    step_id: int
    count: int


class StepColumns(CamelModel):
    """The columns of one search step, each read over the whole step."""

    wdk_step_id: int
    fits: list[ColumnFit] = Field(default_factory=list)
    # What to read instead when no column shows a value the step binds.
    note: str = ""


MAX_SAMPLE_LIMIT = 100


def _validate_download_url_inputs(
    wdk_step_id: int,
    output_format: str,
) -> None:
    """Validate inputs for get_download_url. Raises ModelRetry on bad input."""
    valid_formats = {"csv", "tab", "json"}
    if output_format not in valid_formats:
        msg = (
            f"VALIDATION_ERROR: Invalid output_format {output_format!r}. "
            f"Must be one of: {', '.join(sorted(valid_formats))}."
        )
        raise ModelRetry(msg)
    if wdk_step_id <= 0:
        msg = (
            f"VALIDATION_ERROR: wdk_step_id must be a positive integer "
            f"(got {wdk_step_id})."
        )
        raise ModelRetry(msg)


def _validate_sample_inputs(wdk_step_id: int) -> None:
    """Validate inputs for get_sample_records. Raises ModelRetry on bad input."""
    if wdk_step_id <= 0:
        msg = (
            f"VALIDATION_ERROR: wdk_step_id must be a positive integer "
            f"(got {wdk_step_id})."
        )
        raise ModelRetry(msg)
