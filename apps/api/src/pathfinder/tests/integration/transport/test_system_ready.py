from collections.abc import AsyncIterator

import httpx
import pytest
from assistant_core.platform import db

from pathfinder.platform.health import worker_is_alive
from pathfinder.platform.readiness import (
    _FIXED_SUBSYSTEMS,
    get_readiness,
    reset_readiness,
)
from pathfinder.tests._support.worker_heartbeat import (
    clear_workers,
    insert_worker_heartbeat,
)
from pathfinder.transport.http.routers import health


@pytest.fixture
async def api_ready() -> AsyncIterator[None]:
    """Every process subsystem ready, and one site catalog loaded."""
    state = get_readiness()
    for name in _FIXED_SUBSYSTEMS:
        state.mark_ready(name)
    state.mark_catalog_ready("plasmodb")
    yield
    reset_readiness()


async def test_worker_is_alive_true_for_fresh_heartbeat(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    await clear_workers()
    await insert_worker_heartbeat(age_seconds=5)
    async with db.async_session_factory() as session:
        assert await worker_is_alive(session) is True
    await clear_workers()


async def test_worker_is_alive_false_for_stale_heartbeat(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    await clear_workers()
    await insert_worker_heartbeat(age_seconds=120)
    async with db.async_session_factory() as session:
        assert await worker_is_alive(session) is False
    await clear_workers()


async def test_worker_is_alive_false_when_no_workers(
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner
    await clear_workers()
    async with db.async_session_factory() as session:
        assert await worker_is_alive(session) is False


async def test_system_ready_true_when_api_ready_and_worker_alive(
    client: httpx.AsyncClient,
    api_ready: None,
) -> None:
    del api_ready
    await clear_workers()
    await insert_worker_heartbeat(age_seconds=2)
    resp = await client.get("/health/system")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["apiReady"] is True
    assert body["workerAlive"] is True
    assert body["notReady"] == []
    await clear_workers()


async def test_system_ready_false_when_worker_dead(
    client: httpx.AsyncClient,
    api_ready: None,
) -> None:
    del api_ready
    await clear_workers()
    resp = await client.get("/health/system")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is False
    assert body["apiReady"] is True
    assert body["workerAlive"] is False
    assert "worker" in body["notReady"]


async def test_system_ready_false_when_api_not_ready(
    client: httpx.AsyncClient,
) -> None:
    reset_readiness()
    await clear_workers()
    await insert_worker_heartbeat(age_seconds=2)
    resp = await client.get("/health/system")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is False
    assert body["apiReady"] is False
    assert body["workerAlive"] is True
    await clear_workers()


async def test_readiness_recovers_after_a_transient_db_failure(
    client: httpx.AsyncClient,
    api_ready: None,
) -> None:
    # A past failed ping must not latch: the live ping is the authority.
    del api_ready
    get_readiness().mark_failed("database", "transient blip")
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["readiness"]["database"]["ready"] is True


async def test_system_ready_recovers_after_a_transient_db_failure(
    client: httpx.AsyncClient,
    api_ready: None,
) -> None:
    del api_ready
    await clear_workers()
    await insert_worker_heartbeat(age_seconds=2)
    get_readiness().mark_failed("database", "transient blip")
    resp = await client.get("/health/system")
    assert resp.json()["apiReady"] is True
    await clear_workers()


async def test_a_failed_ping_records_a_non_empty_error(
    client: httpx.AsyncClient,
    api_ready: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # str(TimeoutError()) is empty; the readiness state must still say why.
    del api_ready

    async def _raise(_session: object) -> bool:
        raise TimeoutError

    monkeypatch.setattr(health, "check_database", _raise)
    resp = await client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json()["readiness"]["database"]["error"] == "TimeoutError"


async def test_readiness_is_ok_while_one_site_is_degraded(
    client: httpx.AsyncClient,
    api_ready: None,
) -> None:
    """One dead VEuPathDB site must not take the deployment down."""
    del api_ready
    get_readiness().mark_catalog_failed("veupathdb", "ReadTimeout")

    resp = await client.get("/health/ready")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["degraded"] == ["veupathdb"]
    assert body["notReady"] == []


async def test_readiness_is_503_when_no_catalog_loaded(
    client: httpx.AsyncClient,
    api_ready: None,
) -> None:
    del api_ready
    state = get_readiness()
    state.mark_catalog_failed("plasmodb", "ReadTimeout")
    state.mark_catalog_failed("veupathdb", "ReadTimeout")

    resp = await client.get("/health/ready")

    assert resp.status_code == 503
    body = resp.json()
    assert body["notReady"] == ["catalogs"]
    assert body["degraded"] == ["plasmodb", "veupathdb"]


async def test_readiness_is_503_when_a_process_subsystem_failed(
    client: httpx.AsyncClient,
    api_ready: None,
) -> None:
    del api_ready
    get_readiness().mark_failed("embedding_backend", "OSError")

    resp = await client.get("/health/ready")

    assert resp.status_code == 503
    assert resp.json()["notReady"] == ["embedding_backend"]


async def test_readiness_is_503_when_the_injection_judge_did_not_build(
    client: httpx.AsyncClient,
    api_ready: None,
) -> None:
    """A screening model this deployment cannot reach holds the process back."""
    del api_ready
    get_readiness().mark_failed("input_screening", "OpenAIError: Missing credentials")

    resp = await client.get("/health/ready")

    assert resp.status_code == 503
    assert resp.json()["notReady"] == ["input_screening"]
    assert resp.json()["readiness"]["input_screening"] == {
        "ready": False,
        "error": "OpenAIError: Missing credentials",
    }


async def test_a_deployment_that_screens_nothing_reports_no_screening_subsystem(
    client: httpx.AsyncClient,
    api_ready: None,
) -> None:
    del api_ready

    resp = await client.get("/health/ready")

    assert resp.status_code == 200
    assert resp.json()["readiness"]["input_screening"] is None


async def test_system_ready_names_the_degraded_sites(
    client: httpx.AsyncClient,
    api_ready: None,
) -> None:
    del api_ready
    await clear_workers()
    await insert_worker_heartbeat(age_seconds=2)
    get_readiness().mark_catalog_failed("veupathdb", "ReadTimeout")

    resp = await client.get("/health/system")

    body = resp.json()
    assert body["apiReady"] is True
    assert body["degraded"] == ["veupathdb"]
    await clear_workers()
