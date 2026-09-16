"""Startup returns while the catalogs are still warming, and says so if it dies.

uvicorn binds its socket only after lifespan startup returns, so anything the
lifespan awaits is an outage window: the port is closed, compose dependents
mis-start, and the proxy in front answers 502. The spawned warm-up owns the
readiness report, so its own death has to reach the same report.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from veupathdb.errors import WDKError
from veupathdb.observability.otel import OpenTelemetryObserver

import pathfinder.jobs.app
from pathfinder import main
from pathfinder.jobs import logging_filters
from pathfinder.platform.langfuse import prompts
from pathfinder.platform.readiness import (
    SubsystemStatus,
    get_readiness,
    reset_readiness,
)
from pathfinder.services.export import sweeper

_MISSING_CREDENTIAL = "the deployment holds no key for the screening model"
_UNBUILT = "a disabled screener builds nothing"


class _MissingCredentialError(Exception):
    """The shape a provider client raises when its key is absent."""


@asynccontextmanager
async def _nothing(*_args: object, **_kwargs: object) -> AsyncIterator[None]:
    yield None


class _Registry:
    def checkpoint_types(self) -> tuple[()]:
        return ()


class _ProcrastinateApp:
    def open_async(self) -> Any:
        return _nothing()


class _Site:
    def __init__(self, site_id: str, *, is_portal: bool = False) -> None:
        self.id = site_id
        self.is_portal = is_portal


class _Router:
    def list_sites(self) -> list[_Site]:
        return [_Site("veupathdb", is_portal=True), _Site("plasmodb")]


class _Embedder:
    async def embed_query(self, text: str) -> list[float]:
        del text
        return [0.0]


@pytest.fixture
def offline_warm_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two warm-up steps that reach a network service."""

    async def _study_index() -> None:
        return None

    monkeypatch.setattr(main, "get_embedder", _Embedder)
    monkeypatch.setattr(main, "preload_study_index", _study_index)


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


async def test_the_lifespan_installs_the_client_s_otel_observer(
    isolated_lifespan: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every WDK call this process makes reports through the client's adapter."""
    del isolated_lifespan
    installed: list[object] = []

    async def _no_warm_up() -> None:
        return None

    monkeypatch.setattr(main, "_warm_up_subsystems", _no_warm_up)
    monkeypatch.setattr(main, "set_observer", installed.append)

    app = FastAPI()
    async with main.lifespan(app):
        pass

    assert [type(observer) for observer in installed] == [OpenTelemetryObserver]


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


async def test_a_warm_up_death_outside_its_handlers_fails_the_loading_subsystem(
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

    reset_readiness()


async def test_a_site_that_refuses_is_degraded_and_the_rest_load(
    offline_warm_up: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One dead VEuPathDB site leaves the other catalogs ready."""
    del offline_warm_up
    reset_readiness()

    refusal = WDKError("refused", status=502)

    class _Discovery:
        async def get_catalog(self, site_id: str) -> None:
            if site_id == "veupathdb":
                raise refusal

    monkeypatch.setattr(main, "get_site_router", _Router)
    monkeypatch.setattr(main, "get_discovery_service", _Discovery)

    await main._warm_up_subsystems()

    readiness = get_readiness()
    assert readiness.degraded == ["veupathdb"]
    assert readiness.catalogs["plasmodb"].ready is True
    assert readiness.catalogs["veupathdb"].error == "the site answered with an error"
    reset_readiness()


async def test_the_catalog_retry_ends_with_the_lifespan(
    isolated_lifespan: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A retry that outlived the lifespan would reload catalogs forever."""
    del isolated_lifespan
    reset_readiness()

    async def _no_warm_up() -> None:
        return None

    class _Discovery:
        async def get_catalog(self, site_id: str) -> None:
            del site_id

    monkeypatch.setattr(main, "_warm_up_subsystems", _no_warm_up)
    monkeypatch.setattr(main, "get_discovery_service", _Discovery)

    app = FastAPI()
    async with main.lifespan(app):
        retry = next(
            task for task in asyncio.all_tasks() if task.get_name() == "catalog-retry"
        )
        assert retry.done() is False

    with pytest.raises(asyncio.CancelledError):
        await retry

    reset_readiness()


async def test_the_portal_is_preloaded_after_the_component_sites(
    offline_warm_up: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One build runs at a time, so a slow portal first spends every budget."""
    del offline_warm_up
    reset_readiness()

    class _Discovery:
        async def get_catalog(self, site_id: str) -> None:
            del site_id

    monkeypatch.setattr(main, "get_site_router", _Router)
    monkeypatch.setattr(main, "get_discovery_service", _Discovery)

    await main._warm_up_subsystems()

    assert list(get_readiness().catalogs) == ["plasmodb", "veupathdb"]
    reset_readiness()


class TestTheWarmUpBuildsTheJudge:
    """A model this deployment cannot reach is a 503, not a 500 per message."""

    @staticmethod
    def _ready_but_for_the_warm_up() -> None:
        """The two subsystems the lifespan marks before it spawns the warm-up."""
        reset_readiness()
        get_readiness().mark_ready("database")
        get_readiness().mark_ready("graph_checkpointer")

    async def test_a_built_judge_reports_the_subsystem_ready(
        self,
        offline_warm_up: None,
        input_screening_enabled: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        del offline_warm_up, input_screening_enabled
        self._ready_but_for_the_warm_up()

        class _Discovery:
            async def get_catalog(self, site_id: str) -> None:
                del site_id

        monkeypatch.setattr(main, "get_site_router", _Router)
        monkeypatch.setattr(main, "get_discovery_service", _Discovery)

        await main._warm_up_subsystems()

        readiness = get_readiness()
        assert readiness.input_screening == SubsystemStatus(ready=True)
        assert "input_screening" not in readiness.not_ready
        reset_readiness()

    async def test_a_judge_that_cannot_be_built_fails_the_subsystem(
        self,
        offline_warm_up: None,
        input_screening_enabled: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        del offline_warm_up, input_screening_enabled
        self._ready_but_for_the_warm_up()

        def no_credential() -> None:
            raise _MissingCredentialError(_MISSING_CREDENTIAL)

        class _Discovery:
            async def get_catalog(self, site_id: str) -> None:
                del site_id

        monkeypatch.setattr(main, "warm_up_screening", no_credential)
        monkeypatch.setattr(main, "get_site_router", _Router)
        monkeypatch.setattr(main, "get_discovery_service", _Discovery)

        await main._warm_up_subsystems()

        readiness = get_readiness()
        assert readiness.not_ready == ["input_screening"]
        assert readiness.input_screening == SubsystemStatus(
            ready=False,
            error=_MISSING_CREDENTIAL,
        )
        reset_readiness()

    async def test_a_disabled_screener_reports_no_subsystem(
        self,
        offline_warm_up: None,
        input_screening_disabled: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        del offline_warm_up, input_screening_disabled
        self._ready_but_for_the_warm_up()

        def fail_build() -> None:
            raise AssertionError(_UNBUILT)

        class _Discovery:
            async def get_catalog(self, site_id: str) -> None:
                del site_id

        monkeypatch.setattr(main, "warm_up_screening", fail_build)
        monkeypatch.setattr(main, "get_site_router", _Router)
        monkeypatch.setattr(main, "get_discovery_service", _Discovery)

        await main._warm_up_subsystems()

        readiness = get_readiness()
        assert readiness.input_screening is None
        assert readiness.not_ready == []
        reset_readiness()
