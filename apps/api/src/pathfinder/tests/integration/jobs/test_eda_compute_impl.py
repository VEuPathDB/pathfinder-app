"""The worker impl drives the six-state job and reports progress."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.platform.db import async_session_factory

from pathfinder.ai.graph.runtime import Context
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.jobs.impls import eda_compute_impl
from pathfinder.jobs.impls.eda_compute_impl import run_eda_compute_impl
from pathfinder.jobs.progress import TaskProgressEmitter
from pathfinder.platform.context import veupathdb_auth_token_ctx
from pathfinder.services.research.literature_search import LiteratureSearchService
from pathfinder.services.research.web_search import WebSearchService
from pathfinder.tests.integration.jobs import _eda_wire

_ARGS = _eda_wire.ARGS
_STUDY = _eda_wire.STUDY
_JOB = _eda_wire.JOB
_unbound = _eda_wire.unbound


class _Progress(TaskProgressEmitter):
    """Keeps every update in memory instead of writing it to Postgres."""

    def __init__(self) -> None:
        super().__init__(
            task_id=uuid4(),
            conversation_id=uuid4(),
            session_factory=async_session_factory,
        )
        self.updates: list[tuple[float, str]] = []

    async def update(
        self,
        *,
        percent: float,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        del data
        self.updates.append((percent, message))


def _never_factory() -> Any:
    msg = "the impl must not open a database session"
    raise AssertionError(msg)


@pytest.fixture
def worker_context() -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=_never_factory,
        web_search_service=WebSearchService(),
        literature_search_service=LiteratureSearchService(),
        cancel_event=asyncio.Event(),
    )


@pytest.fixture(autouse=True)
def token() -> Iterator[None]:
    handle = veupathdb_auth_token_ctx.set("t")
    yield
    veupathdb_auth_token_ctx.reset(handle)


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> Any:
    """One installed EDA double, ready for a status sequence."""

    def install(*statuses: str) -> _eda_wire.Wire:
        return _eda_wire.install(monkeypatch, *statuses)

    return install


async def test_the_impl_polls_to_completion_and_returns_a_summary(
    worker_context: Context,
    wire: Any,
) -> None:
    installed = wire("queued", "in-progress", "complete")

    result = await run_eda_compute_impl(
        context=worker_context,
        task_id=uuid4(),
        conversation_id=uuid4(),
        progress=_Progress(),
        memory_store=None,
        **_ARGS,
    )
    await installed.client.close()

    assert result["status"] == "complete"
    assert result["jobId"] == _JOB
    assert result["computeName"] == "differentialexpression"
    assert result["method"] == "DESeq"
    # The recorded slice of the live volcano: the live lane pins 5511/1543.
    assert result["effectSizeLabel"] == "log2(Fold Change)"
    assert result["genesTested"] == 201
    assert result["genesUnreadable"] == 1
    assert result["effectSizeThreshold"] == 1.0
    assert result["significanceThreshold"] == 0.05
    assert result["retained"] == 67
    assert result["retainedUp"] == 33
    assert result["retainedDown"] == 34
    assert result["retained"] == result["retainedUp"] + result["retainedDown"]
    assert "67 of 201" in result["guidance"]


async def test_progress_reports_queued_then_running_then_complete(
    worker_context: Context,
    wire: Any,
) -> None:
    installed = wire("queued", "in-progress", "complete")

    progress = _Progress()
    await run_eda_compute_impl(
        context=worker_context,
        task_id=uuid4(),
        conversation_id=uuid4(),
        progress=progress,
        memory_store=None,
        **_ARGS,
    )
    await installed.client.close()

    percents = [p for p, _m in progress.updates]
    assert percents == sorted(percents)
    assert percents[0] == 0.0
    assert percents[-1] == 1.0
    assert max(percents[1:-1]) < 1.0
    messages = " ".join(m for _p, m in progress.updates)
    assert "queue" in messages.lower()
    assert "complete" in messages.lower()


async def test_a_failed_job_raises_with_the_status_named(
    worker_context: Context,
    wire: Any,
) -> None:
    installed = wire("queued", "failed")

    with pytest.raises(RuntimeError) as excinfo:
        await run_eda_compute_impl(
            context=worker_context,
            task_id=uuid4(),
            conversation_id=uuid4(),
            progress=_Progress(),
            memory_store=None,
            **_ARGS,
        )
    await installed.client.close()
    assert "failed" in str(excinfo.value)


async def test_a_config_the_predicates_reject_never_reaches_the_wire(
    worker_context: Context,
    wire: Any,
) -> None:
    """An out-of-vocabulary group label is accepted at submit and fails later."""
    installed = wire("complete")

    bad = dict(_ARGS)
    bad["group_a_labels"] = ["NOT_A_VALUE"]
    with pytest.raises(ValueError, match="vocabulary") as excinfo:
        await run_eda_compute_impl(
            context=worker_context,
            task_id=uuid4(),
            conversation_id=uuid4(),
            progress=_Progress(),
            memory_store=None,
            **bad,
        )
    await installed.client.close()
    assert "NOT_A_VALUE" in str(excinfo.value)
    assert not any(call.path.startswith("/eda/computes/") for call in installed.calls)


async def test_an_unknown_method_never_reaches_the_wire(
    worker_context: Context,
    wire: Any,
) -> None:
    """DESeq2 is not a value, and the models refuse it before the submit."""
    installed = wire("complete")

    bad = dict(_ARGS)
    bad["method"] = "DESeq2"
    with pytest.raises(ValueError, match="DESeq2"):
        await run_eda_compute_impl(
            context=worker_context,
            task_id=uuid4(),
            conversation_id=uuid4(),
            progress=_Progress(),
            memory_store=None,
            **bad,
        )
    await installed.client.close()
    assert not any(call.path.startswith("/eda/computes/") for call in installed.calls)


async def test_a_cached_job_completes_without_a_poll(
    worker_context: Context,
    wire: Any,
) -> None:
    """The job id is an input hash, so an identical request is already done."""
    installed = wire("complete")

    progress = _Progress()
    result = await run_eda_compute_impl(
        context=worker_context,
        task_id=uuid4(),
        conversation_id=uuid4(),
        progress=progress,
        memory_store=None,
        **_ARGS,
    )
    await installed.client.close()

    assert result["status"] == "complete"
    assert len(progress.updates) <= 3
    assert not any(call.path.startswith("/eda/jobs/") for call in installed.calls)


async def test_a_thread_with_no_open_analysis_names_the_tool_that_opens_one(
    worker_context: Context,
    wire: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed = wire("complete")
    monkeypatch.setattr(eda_compute_impl, "bound_conversation_analysis", _unbound)

    with pytest.raises(ValueError, match="open_eda_analysis") as excinfo:
        await run_eda_compute_impl(
            context=worker_context,
            task_id=uuid4(),
            conversation_id=uuid4(),
            progress=_Progress(),
            memory_store=None,
            **_ARGS,
        )
    await installed.client.close()
    assert "open_eda_analysis" in str(excinfo.value)


async def test_the_submitted_body_carries_the_analysis_subset(
    worker_context: Context,
    wire: Any,
) -> None:
    """The job id hashes the filters, so the step's later read hits the cache."""
    installed = wire("complete")

    await run_eda_compute_impl(
        context=worker_context,
        task_id=uuid4(),
        conversation_id=uuid4(),
        progress=_Progress(),
        memory_store=None,
        **_ARGS,
    )
    await installed.client.close()

    bodies = [
        call.body for call in installed.calls if call.path.startswith("/eda/computes/")
    ]
    assert bodies
    for body in bodies:
        assert body["studyId"] == _STUDY
        assert body["filters"] == [
            {
                "entityId": "ENT_8151325d",
                "variableId": "VAR_081ab087",
                "type": "stringSet",
                "stringSet": ["febrile", "normal"],
            },
        ]


async def test_a_completed_run_records_the_computation_on_the_analysis(
    worker_context: Context,
    wire: Any,
) -> None:
    """create_eda_step refuses an export when the analysis carries none."""
    installed = wire("complete")

    await run_eda_compute_impl(
        context=worker_context,
        task_id=uuid4(),
        conversation_id=uuid4(),
        progress=_Progress(),
        memory_store=None,
        **_ARGS,
    )
    await installed.client.close()

    assert len(installed.applied) == 1
    computation = installed.applied[0]
    config = computation.descriptor.configuration
    assert config.identifier_variable.variable_id == "VEUPATHDB_GENE_ID"
    assert config.comparator.group_a[0].label == "normal"
    assert config.comparator.group_b[0].label == "febrile"
    assert config.differential_expression_method == "DESeq"
    volcano = computation.visualizations[0].descriptor.configuration
    assert volcano.effect_size_threshold == 1.0
    assert volcano.significance_threshold == 0.05


async def test_the_mutated_analysis_reaches_the_thread_under_a_new_revision(
    worker_context: Context,
    wire: Any,
) -> None:
    """Both surfaces order their writes on the revision, so it must move."""
    installed = wire("complete")

    await run_eda_compute_impl(
        context=worker_context,
        task_id=uuid4(),
        conversation_id=uuid4(),
        progress=_Progress(),
        memory_store=None,
        **_ARGS,
    )
    await installed.client.close()

    states = [
        chunk
        for chunk in installed.chunks
        if chunk["type"] == "data-eda.analysis-state"
    ]
    assert len(states) == 1
    data = states[0]["data"]
    assert data["revision"] == 1
    assert data["analysisId"] == _eda_wire.ANALYSIS
    assert data["datasetId"] == _eda_wire.DATASET
    assert data["studyId"] == _eda_wire.STUDY
    assert data["numComputations"] == 1
    assert data["filterSummaries"] == [
        "temperature_condition is one of febrile, normal",
    ]


async def test_the_volcano_carries_the_caption_the_model_wrote(
    worker_context: Context,
    wire: Any,
) -> None:
    """The figure prints the model's sentence, so the impl must forward it."""
    installed = wire("complete")

    await run_eda_compute_impl(
        context=worker_context,
        task_id=uuid4(),
        conversation_id=uuid4(),
        progress=_Progress(),
        memory_store=None,
        caption="Genes higher in febrile samples than in normal samples",
        **_ARGS,
    )
    await installed.client.close()

    viz = [chunk for chunk in installed.chunks if chunk["type"] == "data-eda.viz"]
    assert [chunk["data"]["caption"] for chunk in viz] == [
        "Genes higher in febrile samples than in normal samples"
    ]


async def test_a_compute_with_no_caption_leaves_the_volcano_s_caption_empty(
    worker_context: Context,
    wire: Any,
) -> None:
    installed = wire("complete")

    await run_eda_compute_impl(
        context=worker_context,
        task_id=uuid4(),
        conversation_id=uuid4(),
        progress=_Progress(),
        memory_store=None,
        **_ARGS,
    )
    await installed.client.close()

    viz = [chunk for chunk in installed.chunks if chunk["type"] == "data-eda.viz"]
    assert [chunk["data"]["caption"] for chunk in viz] == [""]


async def test_a_completed_compute_puts_the_volcano_after_the_analysis_state(
    worker_context: Context,
    wire: Any,
) -> None:
    """The card draws the default cut, and the state names its revision first."""
    installed = wire("complete")

    await run_eda_compute_impl(
        context=worker_context,
        task_id=uuid4(),
        conversation_id=uuid4(),
        progress=_Progress(),
        memory_store=None,
        **_ARGS,
    )
    await installed.client.close()

    assert [chunk["type"] for chunk in installed.chunks] == [
        "data-eda.analysis-state",
        "data-eda.viz",
    ]
    data = installed.chunks[1]["data"]
    assert data["chart"] == "volcano"
    assert data["analysisId"] == _eda_wire.ANALYSIS
    assert data["datasetId"] == _eda_wire.DATASET
    assert data["effectSizeLabel"] == "log2(Fold Change)"
    assert data["effectSizeThreshold"] == 1.0
    assert data["significanceThreshold"] == 0.05
    assert data["effectDirection"] == "upAndDown"
    assert data["totalPoints"] == _eda_wire.FIXTURE_ROWS
    assert data["retainedPoints"] == _eda_wire.FIXTURE_RETAINED
    # The recorded row with no p-value is plotted, and the key is null on the
    # wire rather than absent, so the card can count it.
    assert len(data["points"]) == _eda_wire.FIXTURE_ROWS
    assert all("pValue" in point for point in data["points"])
    silent = [point for point in data["points"] if point["pValue"] is None]
    assert silent == [
        {
            "pointId": "PF3D7_MIT04200",
            "effectSize": -1.49447459261845,
            "pValue": None,
            "adjustedPValue": None,
            "retained": False,
        }
    ]
    assert data["points"][0]["retained"] is True
    kept = [point for point in data["points"] if point["retained"]]
    assert len(kept) == _eda_wire.FIXTURE_RETAINED
    assert all(abs(point["effectSize"]) >= 1.0 for point in kept)
    assert all(point["pValue"] <= 0.05 for point in kept)


async def test_a_failed_job_never_announces_a_new_revision(
    worker_context: Context,
    wire: Any,
) -> None:
    """A compute that produced nothing changed nothing to re-render."""
    installed = wire("no-such-job", "failed")

    with pytest.raises(RuntimeError, match="failed"):
        await run_eda_compute_impl(
            context=worker_context,
            task_id=uuid4(),
            conversation_id=uuid4(),
            progress=_Progress(),
            memory_store=None,
            **_ARGS,
        )
    await installed.client.close()

    assert installed.chunks == []
    assert installed.applied == []
