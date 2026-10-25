"""The columns of a step on OrthoMCL, from the recorded record types."""

from __future__ import annotations

import pytest
from veupathdb.wdk import WDKRecordType
from veupathdb_mcp.wdk import StepColumn, StepColumns, transforms_from

from pathfinder.services.experiment import step_tally
from pathfinder.tests._support.orthomcl_record_classes import (
    recorded_orthomcl_record_types,
)


def recorded_step_columns(
    record_types: list[WDKRecordType],
    record_type: str,
    step_id: int,
    search_name: str,
) -> StepColumns:
    held = next(r for r in record_types if r.url_segment == record_type)
    return StepColumns(
        step_id=step_id,
        record_type=record_type,
        search_name=search_name,
        columns=tuple(
            StepColumn(
                name=a.name,
                display_name=a.display_name or a.name,
                data_type=a.column_data_type,
                countable=a.column_data_type in ("STRING", "NUMBER")
                and "byValue" in a.tools.reports,
            )
            for a in held.attributes or []
        ),
        transforms=transforms_from(record_types, record_type),
    )


def serve_step_columns(
    monkeypatch: pytest.MonkeyPatch, record_type: str, step_id: int, search_name: str
) -> list[int]:
    record_types = recorded_orthomcl_record_types()
    listed_for: list[int] = []

    async def list_step_columns(site_id: str, wdk_step_id: int) -> StepColumns:
        del site_id
        listed_for.append(wdk_step_id)
        return recorded_step_columns(record_types, record_type, step_id, search_name)

    async def raw_record_types(site_id: str) -> list[WDKRecordType]:
        del site_id
        return record_types

    monkeypatch.setattr(step_tally, "list_step_columns", list_step_columns)
    monkeypatch.setattr(step_tally, "get_raw_record_types", raw_record_types)
    return listed_for


def serve_sequence_columns(
    monkeypatch: pytest.MonkeyPatch, step_id: int, search_name: str
) -> list[int]:
    return serve_step_columns(monkeypatch, "sequence", step_id, search_name)
