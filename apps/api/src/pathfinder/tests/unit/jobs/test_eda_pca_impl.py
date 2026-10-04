"""The reduction's worker body places the samples on the components the
service computed, keeps the computation on the analysis, and refuses what it
cannot run."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.progress import TaskProgressEmitter
from veupathdb.auth_context import veupathdb_auth_token_ctx

from pathfinder.ai.graph.runtime import Context
from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.domain.statistic_facts import statistic_id
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.jobs.impls import eda_thread_io
from pathfinder.jobs.impls.eda_pca_impl import run_eda_dimensionality_reduction_impl
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.eda_step_doubles import (
    COUNTS_ENTITY,
    SAMPLE_ENTITY,
    binding_of,
    de_analysis,
    de_study,
)
from pathfinder.tests._support.eda_wire import (
    DE_ENTITY_SIZES,
    DE_STUDY,
    AnalysisStore,
    eda_transport,
    wire_eda,
)

_ARGS: dict[str, Any] = {
    "identifier_variable": {
        "entity_id": COUNTS_ENTITY,
        "variable_id": "VEUPATHDB_GENE_ID",
    },
    "value_variable": {
        "entity_id": COUNTS_ENTITY,
        "variable_id": "SEQUENCE_READ_COUNT_SENSE",
    },
    "data_format": "rawCounts",
    "color_by_variable": {"entity_id": SAMPLE_ENTITY, "variable_id": "VAR_84f17484"},
    "caption": "The samples separate by temperature along the first component",
}
_ID = statistic_id(
    "pca",
    [f"{COUNTS_ENTITY}.SEQUENCE_READ_COUNT_SENSE", f"{SAMPLE_ENTITY}.VAR_84f17484"],
)
_JOB = "2679abb0e5c81b345a21b8f211db6a9b"


class _Progress(TaskProgressEmitter):
    def __init__(self) -> None:
        super().__init__(
            task_id=uuid4(),
            conversation_id=uuid4(),
            session_factory=async_session_factory,
        )
        self.messages: list[str] = []

    async def update(
        self, *, percent: float, message: str, data: dict[str, Any] | None = None
    ) -> None:
        del percent, data
        self.messages.append(message)


class _Thread:
    """The thread the body writes to, and the requests it sent the service."""

    def __init__(self) -> None:
        self.chunks: list[dict[str, Any]] = []
        self.requests: dict[str, Any] = {}


@pytest.fixture(autouse=True)
def token() -> Iterator[None]:
    handle = veupathdb_auth_token_ctx.set("t")
    yield
    veupathdb_auth_token_ctx.reset(handle)


def _wire(
    monkeypatch: pytest.MonkeyPatch, *, job_status: str = "complete"
) -> tuple[_Thread, AnalysisStore]:
    detail = de_analysis(filters=[])
    store = AnalysisStore(detail=detail)
    inner = eda_transport(
        study_id=DE_STUDY,
        study_fixture="study_detail_de",
        store=store,
        entity_sizes=DE_ENTITY_SIZES,
    )
    thread = _Thread()

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.content:
            thread.requests[path] = json.loads(request.content)
        if path == "/eda/computes/dimensionalityreduction":
            return httpx.Response(200, json={"jobID": _JOB, "status": job_status})
        return inner.handle_request(request)

    wire_eda(monkeypatch, httpx.MockTransport(handle))

    async def bound(*, conversation_id: UUID) -> ConversationAnalysisView:
        del conversation_id
        return binding_of(detail)

    async def bump(*, conversation_id: UUID) -> int:
        del conversation_id
        return 7

    async def record(*, conversation_id: UUID, chunk: dict[str, Any]) -> int:
        del conversation_id
        thread.chunks.append(chunk)
        return len(thread.chunks)

    monkeypatch.setattr(eda_thread_io, "bound_conversation_analysis", bound)
    monkeypatch.setattr(eda_thread_io, "get_study_detail_for_dataset", de_study)
    monkeypatch.setattr(eda_thread_io, "bump_analysis_revision", bump)
    monkeypatch.setattr(eda_thread_io, "append_chunk", record)
    return thread, store


async def _run(**overrides: Any) -> dict[str, Any]:
    return await run_eda_dimensionality_reduction_impl(
        context=Context(
            site_id="plasmodb",
            user_id=uuid4(),
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
        ),
        task_id=uuid4(),
        conversation_id=uuid4(),
        progress=_Progress(),
        memory_store=None,
        **(_ARGS | overrides),
    )


async def test_the_result_is_the_statistic_the_lead_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch)

    result = await _run()

    assert result["statistic"] == {
        "id": _ID,
        "kind": "pca",
        "title": "PCA of 12 samples",
        "rows": [
            {"name": "PC1", "value": "54.35%"},
            {"name": "PC2", "value": "12.79%"},
            {"name": "samples", "value": "12 samples"},
            {"name": "groups", "value": "3 groups"},
        ],
    }


async def test_the_samples_reach_the_thread_after_the_analysis_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread, _store = _wire(monkeypatch)

    await _run()

    assert [chunk["type"] for chunk in thread.chunks] == [
        "data-eda.analysis-state",
        "data-eda.pca",
    ]
    pca = thread.chunks[1]
    assert pca["id"] == _ID
    data = pca["data"]
    assert data["axes"] == [
        {"variableId": "PC1", "displayName": "PC 1 (54.35% variance)"},
        {"variableId": "PC2", "displayName": "PC 2 (12.79% variance)"},
    ]
    assert [s["label"] for s in data["series"]] == [
        "delta-DHC mutant",
        "delta-LRR5 mutant",
        "wildtype",
    ]
    assert data["series"][0]["sampleIds"] == [
        "PB4_37C_Rep1",
        "PB4_37C_Rep2",
        "PB4_41C_Rep1",
        "PB4_41C_Rep2",
    ]
    assert data["series"][0]["x"][0] == -32.8759958003351
    assert (data["sampleCount"], data["groupCount"]) == (12, 3)
    assert data["caption"] == _ARGS["caption"]
    assert thread.chunks[0]["data"]["numComputations"] == 1


async def test_the_plot_reads_the_components_under_the_compute_s_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread, _store = _wire(monkeypatch)

    await _run()

    body = thread.requests[
        "/eda/apps/dimensionalityreduction/visualizations/scatterplot"
    ]
    assert body["config"] == {
        "outputEntityId": SAMPLE_ENTITY,
        "valueSpec": "raw",
        "xAxisVariable": {"entityId": SAMPLE_ENTITY, "variableId": "PC1"},
        "yAxisVariable": {"entityId": SAMPLE_ENTITY, "variableId": "PC2"},
        "overlayVariable": {"entityId": SAMPLE_ENTITY, "variableId": "VAR_84f17484"},
        "returnPointIds": True,
    }
    assert body["computeConfig"] == {
        "identifierVariable": {
            "entityId": COUNTS_ENTITY,
            "variableId": "VEUPATHDB_GENE_ID",
        },
        "valueVariable": {
            "entityId": COUNTS_ENTITY,
            "variableId": "SEQUENCE_READ_COUNT_SENSE",
        },
        "dataFormat": "rawCounts",
    }


async def test_the_analysis_keeps_the_reduction_and_its_scatterplot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _thread, store = _wire(monkeypatch)

    await _run()

    (computation,) = store.patched[-1]["descriptor"]["computations"]
    assert computation["computationId"] == _JOB
    assert computation["descriptor"]["type"] == "dimensionalityreduction"
    assert computation["descriptor"]["configuration"]["dataFormat"] == "rawCounts"
    assert computation["visualizations"][0]["descriptor"] == {
        "type": "scatterplot",
        "configuration": {
            "valueSpecConfig": "Raw",
            "overlayVariable": {
                "entityId": SAMPLE_ENTITY,
                "variableId": "VAR_84f17484",
            },
        },
    }


async def test_a_color_below_the_samples_is_refused_before_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread, _store = _wire(monkeypatch)

    with pytest.raises(ValueError, match="read from an ancestor entity") as refused:
        await _run(
            color_by_variable={
                "entity_id": COUNTS_ENTITY,
                "variable_id": "SEQUENCE_READ_COUNT_ANTISENSE",
            }
        )

    assert str(refused.value) == (
        f"color_by_variable is on entity {COUNTS_ENTITY}, and a sample's color is "
        f"read from an ancestor entity of {COUNTS_ENTITY}."
    )
    assert thread.chunks == []


async def test_a_value_that_is_no_expression_measurement_is_refused_before_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread, _store = _wire(monkeypatch)

    with pytest.raises(ValueError, match="valueVariable names") as refused:
        await _run(
            value_variable={
                "entity_id": COUNTS_ENTITY,
                "variable_id": "VEUPATHDB_GENE_ID",
            }
        )

    assert str(refused.value).startswith(
        "valueVariable names VEUPATHDB_GENE_ID, and the compute reads only an "
        "expression measurement: "
    )
    assert thread.chunks == []


async def test_a_failed_job_is_refused_with_its_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread, _store = _wire(monkeypatch, job_status="failed")

    with pytest.raises(RuntimeError) as refused:
        await _run()

    assert str(refused.value) == (
        f"The dimensionality-reduction job {_JOB} is failed. The site's "
        f"compute service publishes no reason for a failed job, so the cause is "
        f"not known."
    )
    assert thread.chunks == []


async def test_a_thread_with_no_open_analysis_names_the_tool_that_opens_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch)

    async def unbound(*, conversation_id: UUID) -> None:
        del conversation_id

    monkeypatch.setattr(eda_thread_io, "bound_conversation_analysis", unbound)

    with pytest.raises(ValueError, match="no open EDA analysis") as refused:
        await _run()

    assert str(refused.value) == (
        "This thread has no open EDA analysis, so there is nothing to compute on. "
        "Call open_eda_analysis first."
    )
