"""Export tool response models."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel


class ExportResultResponse(CamelModel):
    """Result of exporting data."""

    download_url: str
    filename: str
    format: str
    item_count: int
    expires_in_seconds: int


class GeneSetSummaryItem(CamelModel):
    """Summary of a gene set for error messages."""

    id: str
    name: str
    gene_count: int
