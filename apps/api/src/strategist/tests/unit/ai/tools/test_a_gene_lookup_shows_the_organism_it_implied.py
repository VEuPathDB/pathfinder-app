from __future__ import annotations

from typing import Any

import pytest
from veupathdb_mcp.catalog import ResolveContext
from veupathdb_mcp.gene_lookup import GeneSearchResult

from strategist.ai.tools.standalone import gene
from strategist.tests._support.tool_returns import returned
from strategist.tests.unit.ai.tools.conftest import agent_run_context

_PF = "Plasmodium falciparum 3D7"


async def test_the_implied_organism_is_shown_and_the_turn_is_the_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[ResolveContext | None] = []

    async def _implied(
        *_args: Any, about: ResolveContext | None, **_kw: Any
    ) -> GeneSearchResult:
        asked.append(about)
        return GeneSearchResult(records=[], total_count=0, implied_organism=_PF)

    monkeypatch.setattr(gene, "lookup_genes_by_text", _implied)
    ctx = agent_run_context()
    ctx.deps.site_id = "plasmodb"
    ctx.deps.agent_state.request_messages = ["falciparum AP2-G"]

    result = await gene.lookup_gene_records(ctx, "falciparum AP2-G")

    assert returned(result, GeneSearchResult).implied_organism == _PF
    assert asked == [ResolveContext(site_id="plasmodb", message="falciparum AP2-G")]
