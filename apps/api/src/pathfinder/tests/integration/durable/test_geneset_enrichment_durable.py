"""The enrichment job runs the real facade, the real enrichment service and the
real export against a stored gene set; only the WDK step calls are answered
from recorded rows."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy import select
from veupathdb.domain.strategy.validation import StepValidation
from veupathdb.json_types import JSONObject
from veupathdb.wdk.wdk_models import (
    WDKStepAnalysisType,
    WDKStepAnalysisTypeResponse,
)
from veupathdb.wdk.wdk_parameters import (
    WDKEnumParam,
    WDKNumberParam,
    WDKParameter,
)
from veupathdb_mcp.wdk.enrichment import service

from pathfinder.jobs.auth_context import attach_user_id
from pathfinder.jobs.impls import register_all_tools
from pathfinder.jobs.impls.geneset_enrichment_impl import (
    run_gene_set_enrichment_impl,
)
from pathfinder.jobs.progress import TaskProgressEmitter
from pathfinder.jobs.registry import TOOL_REGISTRY
from pathfinder.jobs.runner import run_durable_task
from pathfinder.persistence.models import BackgroundTask, GeneSetRow, TaskProgress, User
from pathfinder.persistence.repositories.background_tasks import (
    BackgroundTaskRepository,
    NewBackgroundTask,
)

_STEP_ID = 5
_ORGANISM = "Plasmodium falciparum 3D7"

_STATS: JSONObject = {
    "bgdGenes": "120",
    "resultGenes": "2",
    "percentInResult": "1.7",
    "foldEnrich": "3.48",
    "oddsRatio": "4.12",
    "pValue": "0.0001",
    "benjamini": "0.002",
    "bonferroni": "0.005",
}
_ROWS: dict[str, list[JSONObject]] = {
    "go-enrichment": [
        {"goId": "GO:0004672", "goTerm": "protein kinase activity", **_STATS}
    ],
    "pathway-enrichment": [
        {
            "pathwayId": "kegg_pfa00010",
            "pathwayName": "Glycolysis / Gluconeogenesis",
            **_STATS,
        }
    ],
    "word-enrichment": [
        {"word": "kinase", "pathwayName": "protein kinase, putative", **_STATS}
    ],
}


def _form(analysis_name: str) -> list[WDKParameter]:
    params: list[WDKParameter] = [
        WDKEnumParam(
            name="organism",
            type="single-pick-vocabulary",
            initial_display_value=_ORGANISM,
        ),
        WDKNumberParam(name="pValueCutoff", initial_display_value="0.05"),
    ]
    if analysis_name == "go-enrichment":
        params.append(
            WDKEnumParam(
                name="goAssociationsOntologies",
                type="single-pick-vocabulary",
                initial_display_value="Biological Process",
            )
        )
    return params


class _RecordedWdk:
    """Answers the step calls the enrichment service makes on a stored step."""

    def __init__(self, gene_count: int) -> None:
        self.gene_count = gene_count
        self.analyses: list[tuple[str, JSONObject]] = []

    async def get_step_count(self, step_id: int, user_id: str | None = None) -> int:
        del user_id
        assert step_id == _STEP_ID
        return self.gene_count

    async def get_analysis_type(
        self, step_id: int, analysis_type: str
    ) -> WDKStepAnalysisTypeResponse:
        del step_id
        return WDKStepAnalysisTypeResponse(
            search_data=WDKStepAnalysisType(
                name=analysis_type,
                display_name=analysis_type,
                parameters=_form(analysis_type),
            ),
            validation=StepValidation(level="DISPLAYABLE", is_valid=True),
        )

    async def run_step_analysis(
        self, *, step_id: int, analysis_type: str, parameters: JSONObject
    ) -> JSONObject:
        del step_id
        self.analyses.append((analysis_type, dict(parameters)))
        return {
            "resultData": _ROWS[analysis_type],
            "downloadPath": "/download",
            "pvalueCutoff": "0.05",
        }


async def _seed_user_chat(user_id: UUID, conversation_id: UUID) -> None:
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                id=conversation_id, user_id=user_id, site_id="plasmodb", name=""
            )
        )
        await session.commit()


async def _seed_gene_set(gene_set_id: str, user_id: UUID, gene_ids: list[str]) -> None:
    async with async_session_factory() as session:
        session.add(
            GeneSetRow(
                id=gene_set_id,
                user_id=user_id,
                site_id="plasmodb",
                name="test gene set",
                gene_ids=gene_ids,
                source="paste",
                wdk_step_id=_STEP_ID,
                record_type="transcript",
            )
        )
        await session.commit()


async def _seed_task(task_id: UUID, conversation_id: UUID, user_id: UUID) -> None:
    async with async_session_factory() as session:
        session.add(
            BackgroundTask(
                id=task_id,
                conversation_id=conversation_id,
                user_id=user_id,
                tool_name="geneset_enrichment",
                status="running",
                args={},
                estimated_duration_seconds=120,
            )
        )
        await session.commit()


class _FakeContext:
    def __init__(self, site_id: str) -> None:
        self.site_id = site_id


@pytest.fixture
def recorded_wdk(monkeypatch: pytest.MonkeyPatch) -> _RecordedWdk:
    api = _RecordedWdk(gene_count=2)
    monkeypatch.setattr(service, "get_strategy_api", lambda site_id: api)
    return api


def test_geneset_enrichment_registered_in_registry() -> None:
    register_all_tools()
    assert "geneset_enrichment" in TOOL_REGISTRY
    assert TOOL_REGISTRY["geneset_enrichment"] is run_gene_set_enrichment_impl


@pytest.mark.asyncio
async def test_geneset_enrichment_impl_runs_the_analyses_and_emits_progress(
    db_cleaner: None,
    patch_app_db_engine: None,
    recorded_wdk: _RecordedWdk,
) -> None:
    del db_cleaner, patch_app_db_engine
    user_id = uuid4()
    conversation_id = uuid4()
    task_id = uuid4()
    gs_id = uuid4().hex[:12]
    await _seed_user_chat(user_id, conversation_id)
    await _seed_gene_set(gs_id, user_id, ["PF3D7_1", "PF3D7_2"])
    await _seed_task(task_id, conversation_id, user_id)
    progress = TaskProgressEmitter(
        task_id=task_id,
        conversation_id=conversation_id,
        session_factory=async_session_factory,
    )

    async with attach_user_id(user_id):
        result = await run_gene_set_enrichment_impl(
            context=_FakeContext(site_id="plasmodb"),
            task_id=task_id,
            progress=progress,
            memory_store=None,
            gene_set_id=gs_id,
            enrichment_types=["go_function", "pathway"],
        )

    assert dict(recorded_wdk.analyses) == {
        "go-enrichment": {
            "organism": f'["{_ORGANISM}"]',
            "pValueCutoff": "0.05",
            "goAssociationsOntologies": '["Molecular Function"]',
        },
        "pathway-enrichment": {
            "organism": f'["{_ORGANISM}"]',
            "pValueCutoff": "0.05",
        },
    }
    assert result["geneSetId"] == gs_id
    assert result["geneSetName"] == "test gene set"
    assert result["geneCount"] == 2
    assert result["analysisTypesRun"] == ["go_function", "pathway"]
    assert result["totalSignificantTerms"] == 2
    enrichment_results: list[dict[str, Any]] = result["enrichmentResults"]
    assert [r["analysisType"] for r in enrichment_results] == ["go_function", "pathway"]
    assert enrichment_results[0]["totalGenesAnalyzed"] == 2
    assert enrichment_results[0]["terms"][0]["termId"] == "GO:0004672"
    assert enrichment_results[0]["terms"][0]["fdr"] == 0.002
    assert (
        enrichment_results[1]["terms"][0]["termName"] == "Glycolysis / Gluconeogenesis"
    )
    downloads: dict[str, Any] = result["downloads"]
    assert {k for k in downloads if k != "expiresInSeconds"} == {"csv", "tsv", "json"}
    assert all("/api/v1/exports/" in downloads[k] for k in ("csv", "tsv", "json"))

    async with async_session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(TaskProgress)
                    .where(TaskProgress.task_id == task_id)
                    .order_by(TaskProgress.id)
                )
            ).scalars()
        )
    assert len(rows) >= 2
    assert rows[0].percent <= rows[-1].percent
    assert rows[-1].percent == 1.0


@pytest.mark.asyncio
async def test_geneset_enrichment_impl_missing_gene_set(
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    user_id = uuid4()
    conversation_id = uuid4()
    task_id = uuid4()
    await _seed_user_chat(user_id, conversation_id)
    await _seed_task(task_id, conversation_id, user_id)
    progress = TaskProgressEmitter(
        task_id=task_id,
        conversation_id=conversation_id,
        session_factory=async_session_factory,
    )

    with pytest.raises(LookupError, match="does not exist"):
        await run_gene_set_enrichment_impl(
            context=_FakeContext(site_id="plasmodb"),
            task_id=task_id,
            progress=progress,
            memory_store=None,
            gene_set_id="nope",
        )


@pytest.mark.asyncio
async def test_run_durable_task_wiring_geneset_enrichment(
    db_cleaner: None,
    patch_app_db_engine: None,
    recorded_wdk: _RecordedWdk,
) -> None:
    del db_cleaner, patch_app_db_engine
    register_all_tools()
    user_id = uuid4()
    conversation_id = uuid4()
    gs_id = uuid4().hex[:12]
    await _seed_user_chat(user_id, conversation_id)
    await _seed_gene_set(gs_id, user_id, ["a", "b"])
    args = {"args": [], "kwargs": {"gene_set_id": gs_id, "enrichment_types": ["word"]}}

    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    task_id = await repo.create(
        task=NewBackgroundTask(
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name="geneset_enrichment",
            args=args,
            tool_call_id="call_geneset_enrichment",
            phase_overrides={},
            estimated_duration_seconds=120,
        ),
    )

    await run_durable_task(
        tool_name="geneset_enrichment",
        task_id=str(task_id),
        thread_id=str(conversation_id),
        args=args,
    )

    assert [a for a, _ in recorded_wdk.analyses] == ["word-enrichment"]
    t = await repo.get(task_id=task_id)
    assert t is not None
    assert t.status in ("complete", "resuming", "result_ready")
    assert t.result is not None
    assert t.result["geneSetId"] == gs_id
    assert t.result["totalSignificantTerms"] == 1
    assert t.result["enrichmentResults"][0]["terms"][0]["termId"] == "kinase"
