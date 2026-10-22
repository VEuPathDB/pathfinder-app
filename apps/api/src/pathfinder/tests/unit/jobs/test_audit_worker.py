"""Audits run on a queue and a worker of their own, so a turn never waits for one and their number is capped."""

from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Iterable

import procrastinate
import pytest
from assistant_core.tasks.names import CHAT_TURN_QUEUE
from procrastinate.testing import InMemoryConnector

from pathfinder.jobs.worker import (
    AUDIT_SHUTDOWN_SECONDS,
    serve_workers,
    serving_workers,
)
from pathfinder.platform.config import get_settings
from pathfinder.services.audit.job import AUDIT_QUEUE

_SETTLE_SECONDS = 2.0


def test_the_turn_worker_never_takes_an_audit_and_the_audit_worker_takes_only_audits() -> (
    None
):
    settings = get_settings().model_copy(
        update={"worker_concurrency": 4, "audit_concurrency": 3}
    )
    turns, audits = serving_workers(
        procrastinate.App(connector=InMemoryConnector()), settings
    )

    assert turns.queues == ["chat_turn", "default", "maintenance", "verification"]
    assert (turns.concurrency, turns.install_signal_handlers) == (4, False)
    assert (audits.queues, audits.concurrency, audits.install_signal_handlers) == (
        [AUDIT_QUEUE],
        3,
        False,
    )
    assert audits.shutdown_graceful_timeout == AUDIT_SHUTDOWN_SECONDS == 5.0


async def test_a_turn_runs_while_the_audits_fill_every_slot_they_have() -> None:
    app = procrastinate.App(connector=InMemoryConnector())
    running: list[int] = []
    most = 0
    release = asyncio.Event()
    turn_ran = asyncio.Event()
    two_running = asyncio.Event()

    @app.task(queue=AUDIT_QUEUE, name="audit-probe")
    async def audit(index: int) -> None:
        nonlocal most
        running.append(index)
        most = max(most, len(running))
        if len(running) == 2:
            two_running.set()
        await release.wait()
        running.remove(index)

    @app.task(queue=CHAT_TURN_QUEUE, name="turn-probe")
    async def turn() -> None:
        turn_ran.set()

    settings = get_settings().model_copy(
        update={"worker_concurrency": 1, "audit_concurrency": 2}
    )
    turns, audits = serving_workers(app, settings)
    async with app.open_async():
        for index in range(3):
            await audit.defer_async(index=index)
        await turn.defer_async()
        working = [asyncio.create_task(w.run()) for w in (turns, audits)]
        await asyncio.wait_for(two_running.wait(), _SETTLE_SECONDS)
        await asyncio.wait_for(turn_ran.wait(), _SETTLE_SECONDS)
        held = sorted(running)
        release.set()
        for worker in (turns, audits):
            worker.stop()
        await asyncio.gather(*working)

    assert (held, most) == ([0, 1], 2)


class _Worker:
    def __init__(self, failure: Exception | None = None) -> None:
        self.worker_id: int | None = None
        self.queues: Iterable[str] | None = None
        self.concurrency = 1
        self.install_signal_handlers = False
        self.shutdown_graceful_timeout: float | None = None
        self.failure = failure
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    async def run(self) -> None:
        self.started.set()
        if self.failure is not None:
            raise self.failure
        await self.stopped.wait()

    def stop(self) -> None:
        self.stopped.set()


async def test_a_failing_audit_worker_stops_the_turn_worker_and_the_process() -> None:
    turns, audits = _Worker(), _Worker(RuntimeError("the audit queue is gone"))

    with pytest.raises(RuntimeError, match="the audit queue is gone"):
        await asyncio.wait_for(serve_workers(turns, audits), _SETTLE_SECONDS)

    assert turns.stopped.is_set()


async def test_a_stop_signal_stops_both_workers_at_once() -> None:
    turns, audits = _Worker(), _Worker()
    serving = asyncio.create_task(serve_workers(turns, audits))
    await asyncio.wait_for(audits.started.wait(), _SETTLE_SECONDS)

    os.kill(os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(serving, _SETTLE_SECONDS)

    assert (turns.stopped.is_set(), audits.stopped.is_set()) == (True, True)
