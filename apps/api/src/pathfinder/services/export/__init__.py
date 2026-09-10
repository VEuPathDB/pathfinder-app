"""Export service — generates downloadable files, stores in Postgres with TTL."""

from __future__ import annotations

from functools import cache

from assistant_core.platform.db import async_session_factory

from pathfinder.services.export.service import (
    ExportResult,
    ExportService,
    StoredExport,
)

__all__ = [
    "ExportResult",
    "ExportService",
    "StoredExport",
    "get_export_service",
]


@cache
def get_export_service() -> ExportService:
    """The export service, built once for the process."""
    return ExportService(session_factory=async_session_factory)
