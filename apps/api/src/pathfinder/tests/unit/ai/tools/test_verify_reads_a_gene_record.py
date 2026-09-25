"""VERIFY reads one sampled gene's record on the site the turn runs on, and the
read is a source the turn retrieved."""

from __future__ import annotations

import pytest

from pathfinder.ai.tools.standalone import gene_record
from pathfinder.ai.tools.toolsets.verification import build_toolset
from pathfinder.services.gene_records import read
from pathfinder.services.gene_records.read import GeneRecordSummary
from pathfinder.tests._support.sub_agents import toolset_tool_names
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_RECORD = GeneRecordSummary(
    site_id="plasmodb",
    gene_id="PF3D7_0102200",
    record_url="https://plasmodb.org/plasmo/app/record/gene/PF3D7_0102200",
    organism="Plasmodium falciparum 3D7",
    product="ring-infected erythrocyte surface antigen",
)


async def test_a_sampled_genes_record_is_read_and_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, str]] = []

    async def _read(site_id: str, gene_id: str) -> GeneRecordSummary:
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
