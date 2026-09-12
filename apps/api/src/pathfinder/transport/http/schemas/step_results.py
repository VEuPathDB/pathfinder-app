"""Typed request and response models for step-result browsing endpoints."""

from dataclasses import dataclass
from typing import Annotated

from assistant_core.platform.pydantic_base import CamelModel
from fastapi import Query
from pydantic import JsonValue
from veupathdb.domain import (
    WDKHistogramBin,
    WDKHistogramStatistics,
    WDKRecordIdPart,
    WDKSortDirection,
)

from pathfinder.services.experiment.types.core import Classification


@dataclass
class RecordQueryParams:
    """The query parameters that the record listing endpoints take."""

    offset: int = Query(0, ge=0)
    limit: int = Query(50, ge=1, le=500)
    sort: str | None = None
    sort_dir: Annotated[WDKSortDirection, Query(alias="dir")] = "ASC"
    attributes: str | None = None
    filter_attribute: str | None = Query(None, alias="filterAttribute")
    filter_value: str | None = Query(None, alias="filterValue")


class ClassifiedRecord(CamelModel):
    """WDK record plus optional TP/FP/FN/TN tag from experiment classification."""

    display_name: str
    id: list[WDKRecordIdPart]
    record_class_name: str
    attributes: dict[str, JsonValue]
    tables: dict[str, JsonValue]
    table_errors: list[str]
    classification: Classification | None = None


class RecordsPagination(CamelModel):
    offset: int
    num_records: int


class RecordsMeta(CamelModel):
    """Counts for one page of records.

    A count is optional because WDK does not always publish one, and a client
    that shows zero there states a result nobody measured.
    """

    total_count: int | None = None
    display_total_count: int | None = None
    response_count: int
    pagination: RecordsPagination
    attributes: list[str]
    tables: list[str]


class RecordsResponse(CamelModel):
    records: list[ClassifiedRecord]
    meta: RecordsMeta


class DistributionResponse(CamelModel):
    histogram: list[WDKHistogramBin]
    statistics: WDKHistogramStatistics
