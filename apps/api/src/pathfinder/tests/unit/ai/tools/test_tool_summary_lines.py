"""The summary line each tool writes: the zero it must report, and the exact
text the recorded turn carries."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.domain.strategy.session import StrategySession
from veupathdb.wdk.ai_expression import AiExpressionStatus
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog.param_formatting import ParameterInfo
from veupathdb_mcp.gene_lookup import GeneSearchResult
from veupathdb_mcp.wdk.ai_expression import (
    NO_SUMMARY_ON_THE_SITE,
    GeneExpressionSummary,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.lead import lead_tools
from pathfinder.ai.tools import standalone
from pathfinder.ai.tools.standalone import (
    catalog_discovery,
    eda_analysis,
    eda_catalog,
    eda_compute,
    experiment,
    memory_tools,
    strategy_graph,
    workbench,
)
from pathfinder.services.eda.catalog import StudyCard
from pathfinder.tests.unit.ai.tools.conftest import (
    agent_state_ctx,
    summary_chunks,
    summary_of,
)


class TestASilentZeroReportsEmpty:
    """A call that found nothing says so, because a zero read as a success
    is the failure the reader cannot see."""

    async def test_search_eda_studies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _none(_site: str, _query: str, *, limit: int) -> Any:
            del limit
            return SimpleNamespace(cards=[], guidance="")

        monkeypatch.setattr(eda_catalog, "search_studies", _none)
        returned = await eda_catalog.search_eda_studies(agent_state_ctx(), "heat shock")
        chunk = summary_of(returned)
        assert chunk.data["summary"] == "No study matched heat shock"
        assert chunk.data["status"] == "empty"

    async def test_search_for_searches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _none(*_args: Any, **_kwargs: Any) -> list[Any]:
            return []

        monkeypatch.setattr(catalog, "search_for_searches", _none)
        ctx = agent_state_ctx()
        ctx.deps.agent_state = AgentToolState()
        returned = await standalone.catalog.search_for_searches(ctx, "nothing at all")
        chunk = summary_of(returned)
        assert chunk.data["summary"] == "0 searches"
        assert chunk.data["status"] == "empty"

    async def test_get_parameter_options(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _no_options(*_args: Any, **_kwargs: Any) -> ParameterInfo:
            return ParameterInfo(
                name="organism",
                display_name="Organism",
                type="single-pick-vocabulary",
                required=True,
                is_visible=True,
                help="",
                value_format="",
                allowed_values=[],
            )

        monkeypatch.setattr(catalog_discovery, "read_parameter_options", _no_options)
        ctx = agent_state_ctx()
        ctx.deps.agent_state = AgentToolState()
        ctx.deps.site_id = "plasmodb"
        returned = await catalog_discovery.get_parameter_options(
            ctx, "GenesByText", "organism"
        )
        chunk = summary_of(returned)
        assert chunk.data["summary"] == "organism: 0 options"
        assert chunk.data["status"] == "empty"

    async def test_get_estimated_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _zero(*_args: Any, **_kwargs: Any) -> Any:
            return SimpleNamespace(step_id=132, count=0)

        monkeypatch.setattr(standalone.execution, "get_estimated_size_for_site", _zero)
        ctx = agent_state_ctx()
        ctx.deps.strategy_session.site_id = "plasmodb"
        returned = await standalone.execution.get_estimated_size(ctx, 132)
        chunk = summary_of(returned)
        assert chunk.data["summary"] == "Step 132: 0 records"
        assert chunk.data["status"] == "empty"

    async def test_get_strategy(self) -> None:
        ctx = agent_state_ctx()
        ctx.deps.strategy_session = StrategySession(site_id="plasmodb")
        returned = await strategy_graph.get_strategy(ctx)
        chunk = summary_of(returned)
        assert chunk.data["summary"] == "No strategy yet"
        assert chunk.data["status"] == "empty"

    async def test_get_live_strategy_state(self) -> None:
        ctx = agent_state_ctx()
        ctx.deps.runtime.site_id = "plasmodb"
        ctx.deps.runtime.strategy_session = StrategySession(site_id="plasmodb")
        chunk = summary_of(await lead_tools.get_live_strategy_state(ctx))
        assert chunk.data["summary"] == "No strategy yet"
        assert chunk.data["status"] == "empty"

    async def test_lookup_gene_records(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _none(*_args: Any, **_kwargs: Any) -> GeneSearchResult:
            return GeneSearchResult(records=[], total_count=0)

        monkeypatch.setattr(standalone.gene, "lookup_genes_by_text", _none)
        ctx = agent_state_ctx()
        ctx.deps.site_id = "plasmodb"
        returned = await standalone.gene.lookup_gene_records(ctx, "PfAP2-G")
        chunk = summary_of(returned)
        assert chunk.data["summary"] == "0 genes matched PfAP2-G"
        assert chunk.data["status"] == "empty"

    async def test_get_ai_expression_summary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _absent(site_id: str, gene_id: str) -> GeneExpressionSummary:
            return GeneExpressionSummary(
                site_id=site_id,
                gene_id=gene_id,
                result_status=AiExpressionStatus.EXPERIMENTS_INCOMPLETE,
                num_experiments=41,
                unavailable_reason=NO_SUMMARY_ON_THE_SITE,
            )

        monkeypatch.setattr(standalone.gene, "get_gene_expression_summary", _absent)
        ctx = agent_state_ctx()
        ctx.deps.site_id = "plasmodb"
        returned = await standalone.gene.get_ai_expression_summary(ctx, "PF3D7_0709000")
        chunk = summary_of(returned)
        assert chunk.data["summary"] == "No expression summary for PF3D7_0709000"
        assert chunk.data["status"] == "empty"

    async def test_search_memory(self) -> None:
        ctx = agent_state_ctx()
        ctx.deps.memory_store = None
        ctx.deps.user_id = None
        returned = await memory_tools.search_memory(ctx, "gametocytes")
        chunk = summary_of(returned)
        assert chunk.data["summary"] == "0 memories for gametocytes"
        assert chunk.data["status"] == "empty"

    def test_run_eda_compute(self) -> None:
        chunks = eda_compute._compute_chunks_from_result(
            {"status": "success", "result": {"genesTested": 0}},
            uuid4(),
            "call_1",
        )
        assert (
            summary_chunks(chunks)[0].data["summary"]
            == "0 genes tested, 0 up and 0 down"
        )
        assert summary_chunks(chunks)[0].data["status"] == "empty"

    def test_run_gene_set_enrichment(self) -> None:
        chunks = workbench._enrichment_chunks_from_result(
            {"status": "success", "result": {"analysisTypesRun": ["pathway"]}},
            uuid4(),
            "call_1",
        )
        assert (
            summary_chunks(chunks)[0].data["summary"]
            == "0 enriched terms across 1 analyses"
        )
        assert summary_chunks(chunks)[0].data["status"] == "empty"


class TestThePinnedStrings:
    """The lines the recorded turn carries, written where the numbers are."""

    async def test_search_eda_studies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        card = StudyCard(
            dataset_id="DS_e973eadd57",
            study_id="STUDY_e973eadd57",
            display_name="Heat shock response in sensitive mutants (LRR5, DHC)",
            short_display_name="Heat shock",
            description="",
            source_type="curated",
        )

        async def _three(_site: str, _query: str, *, limit: int) -> Any:
            del limit
            return SimpleNamespace(cards=[card, card, card], guidance="")

        monkeypatch.setattr(eda_catalog, "search_studies", _three)
        returned = await eda_catalog.search_eda_studies(agent_state_ctx(), "heat shock")
        assert summary_of(returned).data["summary"] == "3 studies matched heat shock"

    async def test_open_eda_analysis(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The line names the analysis the researcher named, and nothing after it."""
        name = "Febrile versus normal heat-shock expression"

        async def _study(_site: str, _dataset: str) -> tuple[Any, Any]:
            return SimpleNamespace(), SimpleNamespace()

        async def _bind(_site: str, **_kwargs: Any) -> Any:
            return SimpleNamespace(
                analysis_id="a1",
                study_id="STUDY_e973eadd57",
                display_name=name,
                study_display_name="Heat shock",
                can_export_rows=True,
            )

        monkeypatch.setattr(eda_analysis, "_study", _study)
        monkeypatch.setattr(eda_analysis, "bind_analysis", _bind)
        monkeypatch.setattr(
            eda_analysis,
            "find_gene_entity",
            lambda _study: SimpleNamespace(entity_id="ENT_g", error=None),
        )
        monkeypatch.setattr(
            eda_analysis,
            "analysis_state_chunks_if_changed",
            lambda _state, domain: [DataChunk(type="data-eda.analysis-state", data={})],
        )
        ctx = agent_state_ctx()
        ctx.deps.runtime.site_id = "plasmodb"
        returned = await eda_analysis.open_eda_analysis(ctx, "DS_e973eadd57", name)
        assert summary_of(returned).data["summary"] == f"Opened {name}"

    def test_run_control_tests_on_step(self) -> None:
        chunks = experiment._control_test_chunks_from_result(
            {
                "status": "success",
                "result": {
                    "positiveIntersection": 8,
                    "positiveControlsCount": 10,
                },
            },
            uuid4(),
            "call_4",
        )
        assert summary_chunks(chunks)[0].data == {
            "toolCallId": "call_4",
            "summary": "8 of 10 positive controls recovered",
            "status": "ok",
        }
