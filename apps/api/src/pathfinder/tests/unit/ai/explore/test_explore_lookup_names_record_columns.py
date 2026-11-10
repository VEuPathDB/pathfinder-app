from __future__ import annotations

import pytest
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb_mcp import catalog as mcp_catalog
from veupathdb_mcp import records
from veupathdb_mcp.catalog import RecordTypeInfo
from veupathdb_mcp.embeddings import SemanticIndexUnavailableError
from veupathdb_mcp.records import ColumnMatch

from pathfinder.ai.explore import explore_tools
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import catalog
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned

BUSCO = "BUSCO completeness of each P. falciparum genome"


class _ColumnsShown(CamelModel):
    note: str
    columns: list[ColumnMatch]


class _ColumnsEntry(CamelModel):
    record_columns: _ColumnsShown


def _busco(site_id: str) -> ColumnMatch:
    return ColumnMatch(
        site_id=site_id,
        record_type="organism",
        record_display_name="Organism",
        kind="column",
        name="busco_genome",
        display_name="BUSCO Genomic",
        similarity=0.71,
    )


@pytest.fixture
def ranked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []

    async def searches(
        ctx: RunContext[AgentDeps],
        query: str,
        record_type: str,
        keywords: list[str] | None = None,
        category: str | None = None,
        limit: int = 20,
    ) -> ToolReturn[list[JSONObject]]:
        del ctx, query, record_type, keywords, category, limit
        return ToolReturn(return_value=[{"name": "GenesByTaxon"}])

    async def columns(site_id: str, query: str, top_k: int = 5) -> list[ColumnMatch]:
        del query, top_k
        asked.append(site_id)
        return [_busco(site_id)] if site_id == "veupathdb" else []

    async def record_types(site_id: str) -> list[RecordTypeInfo]:
        names = (
            ["group", "sequence", "helper"]
            if site_id == "orthomcl"
            else ["transcript", "organism"]
        )
        return [RecordTypeInfo(name=name, display_name=name) for name in names]

    monkeypatch.setattr(catalog, "search_for_searches", searches)
    monkeypatch.setattr(records, "rank_record_columns", columns)
    monkeypatch.setattr(mcp_catalog, "get_record_types", record_types)
    return asked


async def _lookup(ctx: RunContext[LeadDeps]) -> ToolReturn[list[JSONObject]]:
    return await explore_tools.search_for_searches(ctx, BUSCO, "transcript")


async def test_the_lookup_names_the_columns_that_hold_the_answer(
    ranked: list[str],
) -> None:
    result = await _lookup(lead_run_context(site_id="veupathdb"))

    rows = returned(result, list[JSONObject])
    assert rows[0] == {"name": "GenesByTaxon"}
    shown = _ColumnsEntry.model_validate(rows[-1]).record_columns
    assert shown.columns == [_busco("veupathdb")]
    assert shown.note.split(", and ")[1].startswith("read_search_table reads")
    assert ranked == ["veupathdb"]


async def test_a_site_without_genes_also_reads_the_portals_columns(
    ranked: list[str],
) -> None:
    result = await _lookup(lead_run_context(site_id="orthomcl"))

    rows = returned(result, list[JSONObject])
    assert ranked == ["orthomcl", "veupathdb"]
    shown = _ColumnsEntry.model_validate(rows[-1]).record_columns
    assert [column.site_id for column in shown.columns] == ["veupathdb"]


async def test_no_close_column_adds_no_block(
    ranked: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def none(site_id: str, query: str, top_k: int = 5) -> list[ColumnMatch]:
        del site_id, query, top_k
        return []

    monkeypatch.setattr(records, "rank_record_columns", none)

    result = await _lookup(lead_run_context(site_id="plasmodb"))

    assert returned(result, list[JSONObject]) == [{"name": "GenesByTaxon"}]


async def test_an_index_that_does_not_answer_adds_no_block(
    ranked: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def down(site_id: str, query: str, top_k: int = 5) -> list[ColumnMatch]:
        del site_id, query, top_k
        raise SemanticIndexUnavailableError

    monkeypatch.setattr(records, "rank_record_columns", down)

    result = await _lookup(lead_run_context(site_id="plasmodb"))

    assert returned(result, list[JSONObject]) == [{"name": "GenesByTaxon"}]
