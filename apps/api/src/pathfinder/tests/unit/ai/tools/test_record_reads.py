from __future__ import annotations

import pytest
from assistant_core.capabilities.refused_calls import CallRefused
from veupathdb_mcp import records
from veupathdb_mcp.record_fields import ColumnInfo
from veupathdb_mcp.records import (
    RecordColumns,
    SearchTable,
    TableRequest,
    TableRow,
    UnreadableRecordError,
)

from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.ai.tools.standalone.record_reads import (
    list_record_columns,
    read_search_table,
)
from pathfinder.domain.read_facts import ReadFact, ReadRow
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

GENOMES = TableRequest(
    record_type="organism",
    search_name="GenomeDataTypes",
    columns=["genecount", "busco_genome"],
    contains="falciparum",
)


def _table(site_id: str) -> SearchTable:
    return SearchTable(
        site_id=site_id,
        record_type="organism",
        search_name="GenomeDataTypes",
        search_display_name="Organisms: Genome Info and Stats",
        table=None,
        columns=[],
        total_records=831,
        matched_rows=0,
        rows=[],
        note="",
    )


async def test_a_table_read_runs_on_the_conversations_site_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, TableRequest]] = []

    async def read(site_id: str, request: TableRequest) -> SearchTable:
        asked.append((site_id, request))
        return _table(site_id)

    monkeypatch.setattr(records, "read_search_table", read)

    result = await read_search_table(agent_run_context(site_id="plasmodb"), GENOMES)

    assert asked == [("plasmodb", GENOMES)]
    assert returned(result, SearchTable).total_records == 831


async def test_a_table_read_may_name_the_portal_from_another_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []

    async def read(site_id: str, request: TableRequest) -> SearchTable:
        del request
        asked.append(site_id)
        return _table(site_id)

    monkeypatch.setattr(records, "read_search_table", read)

    await read_search_table(
        agent_run_context(site_id="orthomcl"), GENOMES, site_id="veupathdb"
    )

    assert asked == ["veupathdb"]


async def test_a_site_this_deployment_does_not_read_is_refused() -> None:
    with pytest.raises(CallRefused, match="not a site this deployment reads"):
        await read_search_table(agent_run_context(), GENOMES, site_id="nosuchdb")


async def test_a_refused_read_is_a_refused_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def refuse(site_id: str, record_type: str) -> RecordColumns:
        msg = f"{site_id} has no record type '{record_type}'. It has: organism."
        raise UnreadableRecordError(msg)

    monkeypatch.setattr(records, "record_columns", refuse)

    with pytest.raises(CallRefused, match="It has: organism"):
        await list_record_columns(agent_run_context(), "organisms")


def _proteomes() -> SearchTable:
    return SearchTable(
        site_id="orthomcl",
        record_type="helper",
        search_name="ByDefault",
        search_display_name="Taxon Helper",
        table="DataSummary",
        columns=[
            ColumnInfo(name="name", display_name="Name"),
            ColumnInfo(name="sequences", display_name="# Proteins"),
            ColumnInfo(name="groups", display_name="# Ortholog Groups"),
        ],
        total_records=1,
        matched_rows=2,
        rows=[
            TableRow(
                record="helper",
                values={
                    "name": "Plasmodium falciparum 3D7",
                    "sequences": "5318",
                    "groups": "3891",
                },
            ),
            TableRow(
                record="helper",
                values={
                    "name": "Plasmodium falciparum Dd2",
                    "sequences": "5257",
                    "groups": "3880",
                },
            ),
        ],
        note="The search returned 1 record. Showing all 2 rows.",
    )


def _genomes() -> SearchTable:
    return SearchTable(
        site_id="veupathdb",
        record_type="organism",
        search_name="GenomeDataTypes",
        search_display_name="Organisms: Genome Info and Stats",
        table=None,
        columns=[
            ColumnInfo(name="organism_full", display_name="Organism"),
            ColumnInfo(name="genecount", display_name="Genes"),
            ColumnInfo(name="busco_genome", display_name="BUSCO Genomic"),
        ],
        total_records=831,
        matched_rows=1,
        rows=[
            TableRow(
                record="Plasmodium falciparum 3D7",
                values={
                    "organism_full": "Plasmodium falciparum 3D7",
                    "genecount": "5720",
                    "busco_genome": "C: 98.3%",
                },
            )
        ],
        note="The search returned 831 records. Showing all 1 rows.",
    )


async def test_each_row_of_a_table_is_a_read_the_turn_shows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def read(site_id: str, request: TableRequest) -> SearchTable:
        del site_id, request
        return _proteomes()

    monkeypatch.setattr(records, "read_search_table", read)
    ctx = agent_run_context(site_id="orthomcl")

    await read_search_table(ctx, GENOMES)

    assert ctx.deps.turn_markers.table_reads == [
        ReadFact(
            title="Taxon Helper",
            rows=[
                ReadRow(
                    label="Rows",
                    value="The search returned 1 record. Showing all 2 rows.",
                )
            ],
        ),
        ReadFact(
            title="Plasmodium falciparum 3D7",
            rows=[
                ReadRow(label="# Proteins", value="5318"),
                ReadRow(label="# Ortholog Groups", value="3891"),
            ],
        ),
        ReadFact(
            title="Plasmodium falciparum Dd2",
            rows=[
                ReadRow(label="# Proteins", value="5257"),
                ReadRow(label="# Ortholog Groups", value="3880"),
            ],
        ),
    ]


async def test_a_row_of_records_is_titled_by_its_record_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def read(site_id: str, request: TableRequest) -> SearchTable:
        del site_id, request
        return _genomes()

    monkeypatch.setattr(records, "read_search_table", read)
    ctx = agent_run_context(site_id="veupathdb")

    await read_search_table(ctx, GENOMES)

    assert ctx.deps.turn_markers.table_reads[1:] == [
        ReadFact(
            title="Plasmodium falciparum 3D7",
            rows=[
                ReadRow(label="Genes", value="5720"),
                ReadRow(label="BUSCO Genomic", value="C: 98.3%"),
            ],
        )
    ]


def test_the_facts_beside_the_reply_show_the_rows_a_table_read_returned() -> None:
    deps = lead_deps(pipeline_state("orthomcl"))
    row = ReadFact(
        title="Plasmodium falciparum 3D7",
        rows=[ReadRow(label="# Proteins", value="5318")],
    )
    deps.turn_markers.record_table_read([row])

    assert turn_facts(deps).reads == [row]
