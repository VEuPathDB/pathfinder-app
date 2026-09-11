"""Generates CSV, TSV, TXT and JSON exports and stores them in Postgres."""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from assistant_core.platform.context import user_id_ctx
from assistant_core.platform.logging import get_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb_mcp.wdk.enrichment import EnrichmentResult, probability_cell, ratio_cell

from pathfinder.persistence.models import Export
from pathfinder.platform.context import request_base_url_ctx
from pathfinder.services.gene_sets.types import GeneSet

logger = get_logger(__name__)

EXPORT_TTL = timedelta(minutes=10)
_EXPORT_TTL_SECONDS = int(EXPORT_TTL.total_seconds())

SessionFactory = Callable[[], AsyncSession]

_ENRICHMENT_HEADER = [
    "analysis_type",
    "term_id",
    "term_name",
    "gene_count",
    "background_count",
    "fold_enrichment",
    "odds_ratio",
    "p_value",
    "fdr",
    "bonferroni",
    "genes",
]


def enrichment_rows(
    results: list[EnrichmentResult],
) -> tuple[list[str], list[list[object]]]:
    """Build the header and the data rows of an enrichment export."""
    rows: list[list[object]] = [
        [
            result.analysis_type,
            term.term_id,
            term.term_name,
            term.gene_count,
            term.background_count,
            ratio_cell(term.fold_enrichment),
            ratio_cell(term.odds_ratio),
            probability_cell(term.p_value),
            probability_cell(term.fdr),
            probability_cell(term.bonferroni),
            ";".join(term.genes),
        ]
        for result in results
        for term in result.terms
    ]
    return list(_ENRICHMENT_HEADER), rows


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Metadata returned after generating an export file."""

    export_id: str
    filename: str
    content_type: str
    url: str
    size_bytes: int
    expires_in_seconds: int


@dataclass(frozen=True, slots=True)
class StoredExport:
    """A persisted export row retrieved for download."""

    id: UUID
    filename: str
    content_type: str
    data: bytes


def _sanitize_filename(name: str) -> str:
    """Strip non-alphanumeric chars from a name for use in filenames."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:60]


def _current_user_id() -> UUID:
    """Return the user_id for the current request; raise if missing."""
    uid = user_id_ctx.get()
    if uid is None:
        msg = "ExportService requires an authenticated user in the request context."
        raise RuntimeError(msg)
    return uid


class ExportService:
    """Generates downloadable files and stores them in Postgres with TTL."""

    def __init__(self, *, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def store(
        self,
        *,
        user_id: UUID,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> UUID:
        """Persist the given bytes for later download by the owner."""
        export_id = uuid4()
        async with self._session_factory() as session:
            session.add(
                Export(
                    id=export_id,
                    user_id=user_id,
                    filename=filename,
                    content_type=content_type,
                    data=data,
                    expires_at=datetime.now(UTC) + EXPORT_TTL,
                )
            )
            await session.commit()
        return export_id

    async def get_export(
        self, *, export_id: UUID, user_id: UUID
    ) -> StoredExport | None:
        """Retrieve a non-expired export row owned by the caller."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(Export).where(
                        Export.id == export_id,
                        Export.user_id == user_id,
                        Export.expires_at > datetime.now(UTC),
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return StoredExport(
                id=row.id,
                filename=row.filename,
                content_type=row.content_type,
                data=bytes(row.data),
            )

    async def _store(
        self, content: bytes, filename: str, content_type: str
    ) -> ExportResult:
        """Persist file bytes for the current user and return export metadata."""
        user_id = _current_user_id()
        export_id = await self.store(
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            data=content,
        )
        logger.info(
            "Export stored",
            export_id=str(export_id),
            filename=filename,
            size_bytes=len(content),
        )
        base = request_base_url_ctx.get() or ""
        return ExportResult(
            export_id=str(export_id),
            filename=filename,
            content_type=content_type,
            url=f"{base}/api/v1/exports/{export_id}",
            size_bytes=len(content),
            expires_in_seconds=_EXPORT_TTL_SECONDS,
        )

    async def export_gene_set(
        self, gene_set: GeneSet, output_format: Literal["csv", "txt"]
    ) -> ExportResult:
        """Export a gene set as CSV or TXT."""
        name_part = _sanitize_filename(gene_set.name or "gene_set")
        if output_format == "txt":
            content = "\n".join(gene_set.gene_ids).encode("utf-8")
            return await self._store(content, f"{name_part}.txt", "text/plain")
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["gene_id"])
        for gid in gene_set.gene_ids:
            writer.writerow([gid])
        return await self._store(
            buf.getvalue().encode("utf-8"), f"{name_part}.csv", "text/csv"
        )

    async def export_enrichment(
        self, results: list[EnrichmentResult], name: str
    ) -> ExportResult:
        """Export enrichment results as CSV."""
        name_part = _sanitize_filename(name or "enrichment")
        header, rows = enrichment_rows(results)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
        return await self._store(
            buf.getvalue().encode("utf-8"), f"{name_part}_enrichment.csv", "text/csv"
        )

    async def export_enrichment_tsv(
        self, results: list[EnrichmentResult], name: str
    ) -> ExportResult:
        """Export enrichment results as TSV."""
        name_part = _sanitize_filename(name or "enrichment")
        header, rows = enrichment_rows(results)
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter="\t")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
        return await self._store(
            buf.getvalue().encode("utf-8"),
            f"{name_part}_enrichment.tsv",
            "text/tab-separated-values",
        )

    async def export_enrichment_json(
        self, results: list[EnrichmentResult], name: str
    ) -> ExportResult:
        """Export enrichment results as JSON."""
        name_part = _sanitize_filename(name or "enrichment")
        serialized = [r.model_dump(by_alias=True) for r in results]
        content = json.dumps(serialized, indent=2).encode("utf-8")
        return await self._store(
            content, f"{name_part}_enrichment.json", "application/json"
        )

    async def export_json(self, data: object, name: str) -> ExportResult:
        """Export arbitrary data as JSON."""
        name_part = _sanitize_filename(name or "export")
        content = json.dumps(data, indent=2, default=str).encode("utf-8")
        return await self._store(content, f"{name_part}.json", "application/json")
