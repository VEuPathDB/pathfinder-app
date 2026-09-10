from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import (
    BackgroundTask,
    Conversation,
    TaskProgressRow,
)
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.progress import TaskProgressEmitter
from sqlalchemy import select

from pathfinder.jobs.impls import optimize_params_impl
from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.parameter_optimization.config import SweepVariantSpec


@dataclass(frozen=True)
class _ProgressRow:
    percent: float
    message: str
    data: dict[str, Any] | None


@dataclass
class _ProgressSink:
    rows: list[_ProgressRow]


@dataclass(frozen=True)
class _FakeContext:
    site_id: str = "plasmodb"


async def _seed_user_chat_task(
    user_id: UUID, conversation_id: UUID, task_id: UUID
) -> None:
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="",
            )
        )
        await session.flush()
        session.add(
            BackgroundTask(
                id=task_id,
                conversation_id=conversation_id,
                user_id=user_id,
                tool_name="optimize_search_parameters",
                status="running",
                args={},
                estimated_duration_seconds=300,
            )
        )
        await session.commit()


async def _read_progress_rows(task_id: UUID) -> list[_ProgressRow]:
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(TaskProgressRow)
                    .where(TaskProgressRow.task_id == task_id)
                    .order_by(TaskProgressRow.id)
                )
            )
            .scalars()
            .all()
        )
    return [
        _ProgressRow(percent=r.percent, message=r.message, data=r.data) for r in rows
    ]


@pytest.fixture
async def progress_sink(
    db_cleaner: None,
    patch_app_db_engine: None,
) -> _ProgressSink:
    """Captures every TaskProgressRow row written during the test.

    Reads from the real ``task_progress`` table after the impl returns, so
    the entire emitter plumbing (batching, NOTIFY, scoped merge) is
    exercised end-to-end.
    """
    del db_cleaner, patch_app_db_engine
    return _ProgressSink(rows=[])


async def _fake_attach_export(result_json: dict[str, Any], search_name: str) -> None:
    """Stand-in for _attach_export — the real one needs a request user_id ctx.

    The export side-effect (write to S3/disk) is genuinely external; mocking
    it here is the same pattern as ``test_optimize_params_durable.py``.
    """
    del search_name
    result_json["downloads"] = {"jsonUrl": "https://ex/sweep.json"}


@pytest.fixture
def run_impl(
    progress_sink: _ProgressSink,
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Returns an awaitable that runs optimize_search_parameters_impl with
    a parameter_space sized to produce ``variants_count`` Cartesian variants.
    """
    monkeypatch.setattr(optimize_params_impl, "_attach_export", _fake_attach_export)

    async def _run(
        *, variants_count: int, max_parallel: int | None = None
    ) -> dict[str, Any]:
        user_id = uuid4()
        conversation_id = uuid4()
        task_id = uuid4()
        await _seed_user_chat_task(user_id, conversation_id, task_id)

        progress = TaskProgressEmitter(
            task_id=task_id,
            conversation_id=conversation_id,
            session_factory=async_session_factory,
        )
        # A categorical with N choices yields N variants in the Cartesian grid.
        choices = [f"c{i}" for i in range(variants_count)]
        target = {
            "site_id": "plasmodb",
            "record_type": "transcript",
            "search_name": "GenesByExpression",
            "fixed_parameters": {},
            "parameter_space": [
                {
                    "name": "knob",
                    "type": "categorical",
                    "choices": choices,
                }
            ],
        }
        controls = {
            "positive_controls": ["a"],
            "negative_controls": [],
            "controls_search_name": "GeneByLocusTag",
            "controls_param_name": "ds_gene_ids",
            "controls_value_format": "newline",
            "controls_extra_parameters": {},
            "id_field": "primary_key",
        }
        settings: dict[str, Any] = {
            "budget": variants_count,
            "objective": "f1",
            "beta": 1.0,
            "method": "grid",
            "estimated_size_penalty": 0.0,
        }
        if max_parallel is not None:
            settings["max_parallel"] = max_parallel

        result = await optimize_params_impl.optimize_search_parameters_impl(
            context=_FakeContext(),
            task_id=task_id,
            progress=progress,
            memory_store=None,
            target=target,
            controls=controls,
            settings=settings,
        )
        await progress.aclose()
        progress_sink.rows.extend(await _read_progress_rows(task_id))
        return result

    return _run


async def test_parallel_fan_out_runs_variants_concurrently(
    monkeypatch: pytest.MonkeyPatch,
    run_impl: Callable[..., Awaitable[dict[str, Any]]],
    progress_sink: _ProgressSink,
) -> None:
    del progress_sink
    in_flight = 0
    max_in_flight = 0

    async def fake_run_trial(
        variant: SweepVariantSpec,
        *,
        progress: TaskProgressEmitter,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        del progress
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        return {"variant_id": variant.id, "status": "success", "score": 0.5}

    monkeypatch.setattr(
        "pathfinder.jobs.impls.optimize_params_impl.run_single_trial",
        fake_run_trial,
    )
    result = await run_impl(variants_count=5)

    assert max_in_flight == 5
    assert len(result["variants"]) == 5
    assert all(v.get("status") == "success" for v in result["variants"])


async def test_partial_failure_continues(
    monkeypatch: pytest.MonkeyPatch,
    run_impl: Callable[..., Awaitable[dict[str, Any]]],
    progress_sink: _ProgressSink,
) -> None:
    del progress_sink

    async def flaky(
        variant: SweepVariantSpec,
        *,
        progress: TaskProgressEmitter,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        del progress
        if variant.id == "v3":
            msg = "boom"
            raise RuntimeError(msg)
        return {"variant_id": variant.id, "status": "success", "score": 0.3}

    monkeypatch.setattr(
        "pathfinder.jobs.impls.optimize_params_impl.run_single_trial",
        flaky,
    )
    result = await run_impl(variants_count=5)

    assert len(result["variants"]) == 5
    failed = [v for v in result["variants"] if v.get("status") == "failed"]
    succeeded = [v for v in result["variants"] if v.get("status") == "success"]
    assert len(failed) == 1
    assert failed[0]["variantId"] == "v3"
    assert "boom" in failed[0]["error"]
    assert len(succeeded) == 4


async def test_per_variant_progress_tags(
    monkeypatch: pytest.MonkeyPatch,
    run_impl: Callable[..., Awaitable[dict[str, Any]]],
    progress_sink: _ProgressSink,
) -> None:
    async def fast(
        variant: SweepVariantSpec,
        *,
        progress: TaskProgressEmitter,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        await progress.update(percent=0.5, message="halfway", data={"trial": 1})
        await progress.update(percent=1.0, message="done", data={"trial": 2})
        return {"variant_id": variant.id, "status": "success", "score": 0.8}

    monkeypatch.setattr(
        "pathfinder.jobs.impls.optimize_params_impl.run_single_trial",
        fast,
    )
    await run_impl(variants_count=3)

    assert len(progress_sink.rows) > 0
    variant_ids = {
        r.data["variantId"]
        for r in progress_sink.rows
        if r.data and "variantId" in r.data
    }
    assert variant_ids == {"v0", "v1", "v2"}


async def test_concurrency_cap_respected(
    monkeypatch: pytest.MonkeyPatch,
    run_impl: Callable[..., Awaitable[dict[str, Any]]],
    progress_sink: _ProgressSink,
) -> None:
    del progress_sink
    active = 0
    max_active = 0

    async def tracker(
        variant: SweepVariantSpec,
        *,
        progress: TaskProgressEmitter,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        del progress
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.1)
        active -= 1
        return {"variant_id": variant.id, "status": "success", "score": 0.1}

    monkeypatch.setattr(
        "pathfinder.jobs.impls.optimize_params_impl.run_single_trial",
        tracker,
    )
    await run_impl(variants_count=10, max_parallel=3)
    assert max_active <= 3
