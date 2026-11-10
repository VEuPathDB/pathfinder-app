"""Reads of records that are not genes: their columns, and one search's rows."""

from __future__ import annotations

from typing import Protocol

from assistant_core.capabilities.refused_calls import CallRefused
from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.types import JSONObject
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.wdk import list_sites
from veupathdb_mcp import catalog, records
from veupathdb_mcp.embeddings import SemanticIndexUnavailableError
from veupathdb_mcp.records import (
    ColumnMatch,
    RecordColumns,
    SearchTable,
    TableRequest,
    TableRow,
    UnreadableRecordError,
)

from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.domain.read_facts import ReadFact, ReadRow

PORTAL = "veupathdb"
_GENES = "transcript"
_COLUMNS_NOTE = (
    "Columns and tables of records that are not genes, nearest the query. A "
    "genome fact such as a gene count or a BUSCO score is one of these. "
    "list_record_columns names the searches that return the record, and "
    "read_search_table reads the column, with site_id when it names another site."
)


class RecordReader(Protocol):
    """What a record read needs of its caller: the site the turn runs on."""

    @property
    def site_id(self) -> str: ...

    @property
    def turn_markers(self) -> TurnMarkers: ...


def _site(ctx: RunContext[RecordReader], site_id: str | None) -> str:
    named = site_id or ctx.deps.site_id
    served = sorted(site.id for site in list_sites())
    if named not in served:
        msg = f"site_id {named!r} is not a site this deployment reads: {served}."
        raise CallRefused(msg)
    return named


async def list_record_columns(
    ctx: RunContext[RecordReader], record_type: str, site_id: str | None = None
) -> ToolReturn[RecordColumns]:
    """List the columns, tables and searches of one record type that is not a gene.

    Genome facts such as gene counts, BUSCO scores and assembly versions are
    columns of the organism record on a genomics site or on the portal
    ('veupathdb'). OrthoMCL keeps its proteome counts in the DataSummary table
    of its helper record. read_search_table reads them.

    Args:
        record_type: A record type the site serves, for example 'organism'.
        site_id: The site to read. Omit it for this conversation's site.
    """
    site = _site(ctx, site_id)
    try:
        listed = await records.record_columns(site, record_type)
    except UnreadableRecordError as exc:
        raise CallRefused(str(exc)) from exc
    summary = (
        f"{count_noun(len(listed.columns), 'column')} and "
        f"{count_noun(len(listed.tables), 'table')} of {record_type} on {site}"
    )
    return with_summary(listed, summary, ctx=ctx)


def _row_fact(table: SearchTable, row: TableRow) -> ReadFact:
    columns = table.columns if table.table is None else table.columns[1:]
    title = row.record if table.table is None else row.values[table.columns[0].name]
    return ReadFact(
        title=title,
        rows=[
            ReadRow(label=c.display_name, value=row.values[c.name])
            for c in columns
            if row.values[c.name] != title
        ],
    )


def _table_facts(table: SearchTable) -> list[ReadFact]:
    heading = ReadFact(
        title=table.search_display_name,
        rows=[ReadRow(label="Rows", value=table.note)],
    )
    return [heading, *(_row_fact(table, row) for row in table.rows)]


async def read_search_table(
    ctx: RunContext[RecordReader], request: TableRequest, site_id: str | None = None
) -> ToolReturn[SearchTable]:
    """Run one search of a record type that is not a gene and read its rows.

    A fact about genomes, proteomes, datasets or other records that are not
    genes comes from here, for example the gene count and BUSCO score of each
    genome of a species from the organism record's GenomeDataTypes search.
    With no table, a row is one record. With a table, a row is one row of that
    table. contains keeps the rows that hold its text, for example a species
    name. The answer names how many rows matched and how many show. A gene
    result is built as a strategy step, never read here.

    Args:
        request: The search, its parameter values, the columns or the table,
            the text rows must hold, and how many rows to show.
        site_id: The site to read. Omit it for this conversation's site.
    """
    site = _site(ctx, site_id)
    try:
        table = await records.read_search_table(site, request)
    except UnreadableRecordError as exc:
        raise CallRefused(str(exc)) from exc
    ctx.deps.turn_markers.record_table_read(_table_facts(table))
    summary = (
        f"{count_noun(len(table.rows), 'row')} of {table.matched_rows} from "
        f"{table.search_display_name} on {site}"
    )
    return with_summary(table, summary, ctx=ctx)


async def _column_sites(site_id: str) -> list[str]:
    held = {info.name for info in await catalog.get_record_types(site_id)}
    return [site_id] if _GENES in held or site_id == PORTAL else [site_id, PORTAL]


async def record_columns_block(site_id: str, query: str) -> JSONObject | None:
    """The record columns nearest a catalog query, or None when none is close.

    A site that holds no genes also ranks the portal's columns, which carry
    every genomics site's genomes.
    """
    found: list[ColumnMatch] = []
    try:
        for site in await _column_sites(site_id):
            found.extend(await records.rank_record_columns(site, query))
    except SemanticIndexUnavailableError:
        return None
    if not found:
        return None
    return {
        "recordColumns": {
            "note": _COLUMNS_NOTE,
            "columns": [match.model_dump(by_alias=True) for match in found],
        }
    }
