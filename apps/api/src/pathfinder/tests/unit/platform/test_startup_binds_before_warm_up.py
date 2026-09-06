"""Startup returns while the catalogs are still warming, and says so if it dies.

uvicorn binds its socket only after lifespan startup returns, so anything the
lifespan awaits is an outage window: the port is closed, compose dependents
mis-start, and the proxy in front answers 502. The spawned warm-up owns the
readiness report, so its own death has to reach the same report.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import FastAPI

import pathfinder.jobs.app
from pathfinder import main
from pathfinder.jobs import logging_filters
from pathfinder.platform import notify_dispatcher
from pathfinder.platform.langfuse import prompts
from pathfinder.platform.readiness import get_readiness, reset_readiness
from pathfinder.services.export import sweeper


@asynccontextmanager
async def _nothing(*_args: object, **_kwargs: object) -> AsyncIterator[None]:
    yield None


class _Registry:
    def checkpoint_types(self) -> tuple[()]:
        return ()


class _ProcrastinateApp:
    def open_async(self) -> Any:
        return _nothing()


@pytest.fixture
def isolated_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every dependency of the lifespan except the warm-up itself."""

    async def _init_db() -> None:
        return None

    async def _sweeper_loop() -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "init_db", _init_db)
    monkeypatch.setattr(main, "setup_logging", lambda: None)
    monkeypatch.setattr(main, "setup_observability", lambda **_kwargs: None)
    monkeypatch.setattr(main, "shutdown_observability", lambda: None)
    monkeypatch.setattr(main, "get_engine", lambda: None)
    monkeypatch.setattr(main, "close_db", _init_db)
    monkeypatch.setattr(main, "close_all_clients", _init_db)
    monkeypatch.setattr(main, "get_assistant_registry", _Registry)
    monkeypatch.setattr(main, "lifespan_checkpointer", _nothing)
    monkeypatch.setattr(main, "lifespan_memory_store", _nothing)
    monkeypatch.setattr(
        logging_filters, "install_procrastinate_redaction", lambda: None
    )
    monkeypatch.setattr(prompts, "seed_prompts", lambda: None)
    monkeypatch.setattr(notify_dispatcher, "lifespan_notify_dispatcher", _nothing)
    monkeypatch.setattr(pathfinder.jobs.app, "procrastinate_app", _ProcrastinateApp())
    monkeypatch.setattr(sweeper, "run_sweeper_loop", _sweeper_loop)


async def test_startup_returns_while_warm_up_still_runs(
    isolated_lifespan: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del isolated_lifespan
    entered = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()

    async def slow_warm_up() -> None:
        entered.set()
        await release.wait()
        finished.set()

    monkeypatch.setattr(main, "_warm_up_subsystems", slow_warm_up)

    app = FastAPI()
    async with main.lifespan(app):
        await entered.wait()
        assert not finished.is_set()
        release.set()
        await finished.wait()

    assert finished.is_set()


async def test_the_lifespan_leaves_the_process_s_logging_alone(
    isolated_lifespan: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The suite shares one process, so a run must add no root log handler."""
    del isolated_lifespan

    async def _no_warm_up() -> None:
        return None

    monkeypatch.setattr(main, "_warm_up_subsystems", _no_warm_up)
    before = list(logging.getLogger().handlers)

    app = FastAPI()
    async with main.lifespan(app):
        pass

    assert logging.getLogger().handlers == before


async def test_the_blocking_model_load_leaves_the_event_loop_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``warm_up_scanner`` holds the CPU for seconds, so it belongs on a thread."""
    callers: list[str] = []

    def record_model() -> None:
        callers.append(threading.current_thread().name)

    class _Discovery:
        async def preload_all(self, readiness: object = None) -> None:
            del readiness

    monkeypatch.setattr(main, "warm_up_scanner", record_model)
    monkeypatch.setattr(main, "get_discovery_service", _Discovery)

    await main._warm_up_subsystems()
    reset_readiness()

    assert callers
    assert all(name != threading.main_thread().name for name in callers)


async def test_a_warm_up_death_outside_its_handlers_fails_the_loading_subsystems(
    isolated_lifespan: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A type no warm-up step catches still reaches ``/health/ready``."""
    del isolated_lifespan
    reset_readiness()
    died = asyncio.Event()

    async def exploding_warm_up() -> None:
        msg = "catalog index divided by zero"
        try:
            raise ZeroDivisionError(msg)
        finally:
            died.set()

    monkeypatch.setattr(main, "_warm_up_subsystems", exploding_warm_up)

    app = FastAPI()
    async with main.lifespan(app):
        await died.wait()
        await asyncio.sleep(0)
        readiness = get_readiness()
        assert readiness.embedding_backend.ready is False
        assert (
            readiness.embedding_backend.error
            == "ZeroDivisionError: catalog index divided by zero"
        )
        assert (
            readiness.piguard.error
            == "ZeroDivisionError: catalog index divided by zero"
        )

    reset_readiness()
