from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.progress import TaskProgressEmitter
from veupathdb.auth_context import veupathdb_auth_token_ctx

from strategist.ai.graph.runtime import Context
from strategist.domain.strategy.session import StrategySession
from strategist.jobs.impls.eda_compute_impl import run_eda_compute_impl
from strategist.tests._support.database import no_database
from strategist.tests._support.eda_wire import DE_ENTITY_SIZES, entity_size
from strategist.tests.integration.jobs import _eda_wire

UPSTREAM_TEXT = "upstream secret text"
GROUP_READ_FILTERS = 2
RECORDED_FAILED_JOB = json.loads(
    (
        Path(__file__).parents[2] / "fixtures" / "eda" / "group_sample_counts.json"
    ).read_text()
)["failedJob"]["body"]

Counted = Callable[[httpx.Request], httpx.Response]


def _whole_or(request: httpx.Request, group: Counted) -> httpx.Response:
    if len(json.loads(request.content)["filters"]) < GROUP_READ_FILTERS:
        return entity_size(request.url.path, DE_ENTITY_SIZES)
    return group(request)


def _counts(normal: int, febrile: int) -> Counted:
    def group(request: httpx.Request) -> httpx.Response:
        labels = json.loads(request.content)["filters"][-1]["stringSet"]
        return httpx.Response(
            200, json={"count": normal if labels == ["normal"] else febrile}
        )

    return lambda request: _whole_or(request, group)


def _refused_counts(request: httpx.Request) -> httpx.Response:
    return _whole_or(request, lambda _group: httpx.Response(500, text=UPSTREAM_TEXT))


@pytest.fixture(autouse=True)
def token() -> Iterator[None]:
    handle = veupathdb_auth_token_ctx.set("t")
    yield
    veupathdb_auth_token_ctx.reset(handle)


async def _run(wire: _eda_wire.Wire, **overrides: Any) -> dict[str, Any]:
    context = Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )

    class Silent(TaskProgressEmitter):
        async def update(
            self,
            *,
            percent: float,
            message: str,
            data: dict[str, Any] | None = None,
        ) -> None:
            del percent, message, data

    try:
        return await run_eda_compute_impl(
            context=context,
            task_id=uuid4(),
            conversation_id=uuid4(),
            progress=Silent(
                task_id=uuid4(),
                conversation_id=uuid4(),
                session_factory=async_session_factory,
            ),
            memory_store=None,
            **{**_eda_wire.ARGS, **overrides},
        )
    finally:
        await wire.client.close()


def _started(wire: _eda_wire.Wire) -> bool:
    return any(
        call.path == "/eda/computes/differentialexpression" and call.autostart
        for call in wire.calls
    )


async def test_no_replicate_in_either_group_is_refused_before_a_job_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _eda_wire.install(monkeypatch, "no-such-job", sample_count=_counts(1, 1))

    with pytest.raises(ValueError, match="No DESeq job started") as refused:
        await _run(wire)

    assert "group A (normal) holds 1 sample" in str(refused.value)
    assert "group B (febrile) holds 1 sample" in str(refused.value)
    assert not _started(wire)


async def test_an_empty_group_is_refused_before_a_job_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _eda_wire.install(monkeypatch, "no-such-job", sample_count=_counts(0, 31))

    with pytest.raises(ValueError, match="group A \\(normal\\) holds 0 samples"):
        await _run(wire)

    assert not _started(wire)


async def test_one_sample_against_a_group_with_replicates_reaches_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _eda_wire.install(
        monkeypatch, "no-such-job", "queued", "complete", sample_count=_counts(1, 31)
    )

    result = await _run(wire)

    assert result["status"] == "complete"
    assert _started(wire)


async def test_one_sample_against_replicates_that_fails_states_the_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _eda_wire.install(
        monkeypatch, "no-such-job", "failed", sample_count=_counts(1, 31)
    )

    with pytest.raises(RuntimeError) as failed:
        await _run(wire)

    assert (
        "group A (normal) holds 1 sample and group B (febrile) holds 31 samples."
    ) in str(failed.value)
    assert "the cause is not known" in str(failed.value)


async def test_two_samples_in_each_group_reach_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _eda_wire.install(
        monkeypatch, "no-such-job", "queued", "complete", sample_count=_counts(2, 2)
    )

    result = await _run(wire)

    assert result["status"] == "complete"
    assert _started(wire)


async def test_a_job_the_service_already_completed_is_not_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _eda_wire.install(monkeypatch, "complete", sample_count=_counts(1, 1))

    result = await _run(wire)

    assert result["status"] == "complete"
    assert not _started(wire)


async def test_limma_reaches_the_job_with_one_sample_in_a_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _eda_wire.install(
        monkeypatch, "no-such-job", "queued", "complete", sample_count=_counts(1, 1)
    )

    result = await _run(wire, method="limma")

    assert result["status"] == "complete"
    assert _started(wire)


async def test_a_failed_job_with_replicates_states_the_counts_and_no_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = RECORDED_FAILED_JOB["jobID"]
    monkeypatch.setattr(_eda_wire, "JOB", job)
    wire = _eda_wire.install(
        monkeypatch, "no-such-job", "failed", sample_count=_counts(4, 31)
    )

    with pytest.raises(RuntimeError) as failed:
        await _run(wire)

    assert str(failed.value) == (
        f"The differential-expression job {job} is failed. The site's compute "
        f"service publishes no reason for a failed job, so the cause is not known. "
        f"In this analysis, group A (normal) holds 4 samples and group B (febrile) "
        f"holds 31 samples. A job id is a hash of the request and the service does "
        f"not run a failed job again, so the same arguments return this same job."
    )


async def test_a_count_read_that_fails_does_not_block_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _eda_wire.install(
        monkeypatch, "no-such-job", "queued", "complete", sample_count=_refused_counts
    )

    result = await _run(wire)

    assert result["status"] == "complete"
    assert _started(wire)


async def test_a_failed_job_with_no_count_states_no_counts_and_no_upstream_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _eda_wire.install(
        monkeypatch, "no-such-job", "failed", sample_count=_refused_counts
    )

    with pytest.raises(RuntimeError) as failed:
        await _run(wire)

    assert str(failed.value) == (
        f"The differential-expression job {_eda_wire.JOB} is failed. The site's "
        f"compute service publishes no reason for a failed job, so the cause is "
        f"not known. A job id is a hash of the request and the service does not "
        f"run a failed job again, so the same arguments return this same job."
    )
