"""The worker runs jobs in parallel up to the configured concurrency."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import procrastinate
import pytest
from procrastinate.testing import InMemoryConnector

from pathfinder.jobs.worker import WorkerCannotScreenError, amain
from pathfinder.platform.config import Settings

_OVERLAP_TIMEOUT_SECONDS = 0.25
_MISSING_CREDENTIAL = "the deployment holds no key for the screening model"
_UNBUILT = "a disabled screener builds nothing"


class _MissingCredentialError(Exception):
    """The shape a provider client raises when its key is absent."""


def _default_worker_concurrency() -> int:
    """The shipped default that the worker entry point passes to procrastinate."""
    return int(Settings.model_fields["worker_concurrency"].get_default())


async def _run_two_jobs(concurrency: int) -> list[str]:
    """Defer two jobs on an in-memory app and return their ordered start/end marks.

    Each job marks its start, waits for the other job to start, then marks its
    end. A job that waits alone gives up after the timeout.
    """
    app = procrastinate.App(connector=InMemoryConnector())
    marks: list[str] = []
    both_started = asyncio.Event()

    @app.task(queue="probe", name="probe")
    async def probe(index: int) -> None:
        marks.append(f"start-{index}")
        if sum(1 for mark in marks if mark.startswith("start-")) == 2:
            both_started.set()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(both_started.wait(), _OVERLAP_TIMEOUT_SECONDS)
        marks.append(f"end-{index}")

    async with app.open_async():
        await probe.defer_async(index=1)
        await probe.defer_async(index=2)
        await app.run_worker_async(
            queues=["probe"],
            concurrency=concurrency,
            wait=False,
            listen_notify=False,
            install_signal_handlers=False,
        )
    return marks


async def test_two_jobs_overlap_at_the_default_concurrency() -> None:
    """The second job starts while the first one still runs."""
    marks = await _run_two_jobs(_default_worker_concurrency())

    assert sorted(marks) == ["end-1", "end-2", "start-1", "start-2"]
    assert marks.index("start-2") < marks.index("end-1")


async def test_second_job_waits_at_concurrency_one() -> None:
    """The second job starts only after the first one ends."""
    marks = await _run_two_jobs(1)

    assert marks == ["start-1", "end-1", "start-2", "end-2"]


@contextlib.asynccontextmanager
async def _noop_open() -> AsyncIterator[None]:
    yield


@dataclass
class _AmainRun:
    """What ``amain`` built, and the order it did the startup work in."""

    worker_kwargs: dict[str, Any]
    heartbeat_kwargs: dict[str, Any]
    marks: list[str]
    ran: bool


def _record(marks: list[str]) -> Callable[[], None]:
    """A judge builder that records the moment it ran."""

    def build() -> None:
        marks.append("build")

    return build


async def _run_amain(
    *,
    worker_concurrency: int = 4,
    heartbeat_interval: float = 5.0,
    screening: bool = False,
    build_judge: Callable[[], None] | None = None,
    marks: list[str] | None = None,
) -> _AmainRun:
    """Run ``amain`` against a stubbed app and report what it built."""
    app = MagicMock()
    app.open_async = MagicMock(side_effect=_noop_open)
    app.perform_import_paths = MagicMock()
    built: dict[str, Any] = {}
    heartbeat_built: dict[str, Any] = {}
    marks = [] if marks is None else marks

    def make_worker(**kwargs: Any) -> MagicMock:
        built.update(kwargs)
        worker = MagicMock()
        worker.worker_id = 11
        worker.run = AsyncMock(side_effect=lambda: marks.append("run"))
        return worker

    def make_heartbeat(**kwargs: Any) -> MagicMock:
        heartbeat_built.update(kwargs)
        heartbeat = MagicMock()
        heartbeat.start = MagicMock(side_effect=lambda: marks.append("start"))
        heartbeat.stop = MagicMock(side_effect=lambda: marks.append("stop"))
        return heartbeat

    with (
        patch("pathfinder.jobs.worker.procrastinate_app", app),
        patch("pathfinder.jobs.worker.setup_logging"),
        patch("pathfinder.jobs.worker.install_procrastinate_redaction"),
        patch("pathfinder.jobs.worker.register_all_tools"),
        patch("pathfinder.jobs.worker.install_admitted_sources"),
        patch("pathfinder.jobs.worker.admitted_tool_sources", return_value=[]),
        patch("pathfinder.jobs.worker.postgres_beat_writer", return_value="writer"),
        patch(
            "pathfinder.jobs.worker.warm_up_screening",
            side_effect=build_judge or _record(marks),
        ),
        patch("pathfinder.jobs.worker.Worker", side_effect=make_worker),
        patch("pathfinder.jobs.worker.HeartbeatThread", side_effect=make_heartbeat),
        patch(
            "pathfinder.jobs.worker.get_settings",
            return_value=MagicMock(
                worker_concurrency=worker_concurrency,
                worker_heartbeat_interval_seconds=heartbeat_interval,
                database_url="postgresql+asyncpg://user@host/db",
                input_screening_enabled=screening,
            ),
        ),
    ):
        await amain()
    return _AmainRun(
        worker_kwargs=built,
        heartbeat_kwargs=heartbeat_built,
        marks=marks,
        ran=True,
    )


async def test_amain_passes_configured_concurrency() -> None:
    """``amain`` hands the configured concurrency to the procrastinate worker."""
    run = await _run_amain(worker_concurrency=6)

    assert run.worker_kwargs["concurrency"] == 6


async def test_amain_keeps_serving_every_queue() -> None:
    """Concurrency does not change the set of queues the worker consumes."""
    run = await _run_amain()

    assert run.worker_kwargs["queues"] == [
        "chat_turn",
        "default",
        "maintenance",
        "verification",
    ]


async def test_amain_beats_around_the_worker_run() -> None:
    """The heartbeat starts before the jobs and stops after them."""
    run = await _run_amain()

    assert run.marks == ["start", "run", "stop"]


async def test_amain_gives_the_heartbeat_the_worker_id_and_interval() -> None:
    """The heartbeat refreshes the row the worker registered, at the interval."""
    run = await _run_amain(heartbeat_interval=2.5)

    assert run.heartbeat_kwargs["interval_seconds"] == 2.5
    assert run.heartbeat_kwargs["worker_id"]() == 11
    assert run.worker_kwargs["update_heartbeat_interval"] == 2.5


class TestTheWorkerBuildsTheJudgeBeforeItConsumesAJob:
    """Every tool result this process reads crosses the judge."""

    async def test_the_judge_is_built_before_the_worker_runs(self) -> None:
        run = await _run_amain(screening=True)

        assert run.marks == ["build", "start", "run", "stop"]

    async def test_a_judge_that_cannot_be_built_stops_the_worker(self) -> None:
        """A worker that cannot screen must not pull a job."""
        marks: list[str] = []

        def no_credential() -> None:
            marks.append("build")
            raise _MissingCredentialError(_MISSING_CREDENTIAL)

        with pytest.raises(WorkerCannotScreenError):
            await _run_amain(screening=True, build_judge=no_credential, marks=marks)

        assert marks == ["build"]

    async def test_a_disabled_screener_builds_nothing_and_the_worker_runs(
        self,
    ) -> None:
        def fail_build() -> None:
            raise AssertionError(_UNBUILT)

        run = await _run_amain(screening=False, build_judge=fail_build)

        assert run.marks == ["start", "run", "stop"]
