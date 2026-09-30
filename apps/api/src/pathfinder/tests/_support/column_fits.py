"""A column fit as a check of a transmembrane step reads it."""

from __future__ import annotations

from pathfinder.domain.evidence import ColumnFit

TM_CRITERION = "two or more transmembrane domains"


def tm_fit(fitting: int, total: int, *, wdk_step_id: int = 441031663) -> ColumnFit:
    """``fitting`` of ``total`` genes hold 2 to 99 transmembrane domains."""
    return ColumnFit(
        criterion_id="c_tm",
        criterion_text=TM_CRITERION,
        wdk_step_id=wdk_step_id,
        column="tm_count",
        display_name="# TM Domains",
        bound_value="2 to 99",
        total=total,
        fitting=fitting,
        fitting_at_most=fitting,
    )
