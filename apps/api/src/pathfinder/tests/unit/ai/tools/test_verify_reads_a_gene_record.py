"""One gene's record is read on the site the turn runs on, and the
read is a source the turn retrieved."""

from __future__ import annotations

import pytest

from pathfinder.ai.graph.turn_records import ReadRecord
from pathfinder.ai.tools.standalone import gene_record
from pathfinder.ai.tools.toolsets.verification import build_toolset
from pathfinder.services.gene_records import read
from pathfinder.services.gene_records.read import GeneRecordSummary, OrthologRow
from pathfinder.tests._support.sub_agents import toolset_tool_names
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_RECORD = GeneRecordSummary(
    site_id="plasmodb",
    gene_id="PF3D7_0102200",
    record_url="https://qa.plasmodb.org/plasmo.qa/app/record/gene/PF3D7_0102200",
    organism="Plasmodium falciparum 3D7",
    product="ring-infected erythrocyte surface antigen",
)


async def test_a_sampled_genes_record_is_read_and_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, str]] = []

    async def _read(
        site_id: str, gene_id: str, *, ortholog_organism: str | None = None
    ) -> GeneRecordSummary:
        del ortholog_organism
        asked.append((site_id, gene_id))
        return _RECORD

    monkeypatch.setattr(read, "read_gene_record", _read)
    ctx = agent_run_context()

    result = await gene_record.read_gene_record(ctx, "PF3D7_0102200")

    assert asked == [("plasmodb", "PF3D7_0102200")]
    assert returned(result, GeneRecordSummary).product == (
        "ring-infected erythrocyte surface antigen"
    )
    assert ctx.deps.turn_markers.retrieved_sources == [_RECORD.record_url]


def test_verify_carries_the_record_read() -> None:
    assert "read_gene_record" in toolset_tool_names(build_toolset())


def _with_one_ortholog(monkeypatch: pytest.MonkeyPatch, asked: str | None) -> None:
    record = _RECORD.model_copy(
        update={
            "orthologs": [
                OrthologRow(organism="Anopheles gambiae PEST", gene_id="AGAP009262")
            ],
            "ortholog_count": 1,
            "ortholog_organism": asked,
        }
    )

    async def _read(
        site_id: str, gene_id: str, *, ortholog_organism: str | None = None
    ) -> GeneRecordSummary:
        del site_id, gene_id, ortholog_organism
        return record

    monkeypatch.setattr(read, "read_gene_record", _read)


async def test_the_record_a_read_returned_is_the_turns_without_its_ortholog_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_one_ortholog(monkeypatch, None)
    ctx = agent_run_context()

    await gene_record.read_gene_record(ctx, "PF3D7_0102200")

    assert ctx.deps.turn_markers.records_retrieved == [
        ReadRecord(
            record_id="PF3D7_0102200",
            url=_RECORD.record_url,
            product="ring-infected erythrocyte surface antigen",
            organism="Plasmodium falciparum 3D7",
        )
    ]


async def test_the_orthologs_of_the_organism_a_read_asked_for_are_the_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_one_ortholog(monkeypatch, "Anopheles gambiae PEST")
    ctx = agent_run_context()

    await gene_record.read_gene_record(
        ctx, "PF3D7_0102200", ortholog_organism="Anopheles gambiae PEST"
    )

    assert [r.asked_orthologs for r in ctx.deps.turn_markers.records_retrieved] == [
        ["AGAP009262", "Anopheles gambiae PEST"]
    ]
