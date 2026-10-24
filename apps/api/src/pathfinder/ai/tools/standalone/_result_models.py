"""The step-result tools' own result shape, and the input each one refuses."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from pydantic_ai.exceptions import ModelRetry

from pathfinder.domain.column_fit import ColumnFit
from pathfinder.domain.expression_fit import ExpressionFit


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
    expression_fit: ExpressionFit | None = None


def no_column(wdk_step_id: int, why: str) -> tuple[StepColumns, str]:
    columns = StepColumns(
        wdk_step_id=wdk_step_id,
        note=f"{why} Sample the root with get_sample_records for this criterion.",
    )
    return columns, f"No column of step {wdk_step_id}"


def _unread_reason(wdk_step_id: int, fit: ColumnFit) -> str:
    column = f"{fit.display_name} ({fit.column})"
    if fit.refused_status is not None:
        return (
            f"The site refused the report of {column} on step {wdk_step_id} "
            f"(HTTP {fit.refused_status})."
        )
    return f"No record of step {wdk_step_id} holds a value of {column}."


def unread_note(wdk_step_id: int, unread: list[ColumnFit]) -> str:
    reasons = " ".join(_unread_reason(wdk_step_id, fit) for fit in unread)
    names = ", ".join(fit.column for fit in unread)
    return (
        f"{reasons} Sample step {wdk_step_id} with get_sample_records and read "
        f"{names} on its records for this criterion."
    )


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
