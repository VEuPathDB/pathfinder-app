"""Health check endpoints."""

from datetime import UTC, datetime

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from pathfinder import __version__
from pathfinder.platform.config import get_settings
from pathfinder.platform.health import check_database, worker_is_alive
from pathfinder.platform.readiness import get_readiness
from pathfinder.transport.http.schemas import HealthResponse, SystemConfigResponse
from pathfinder.transport.http.schemas.health import (
    ProviderStatus,
    ReadinessResponse,
    SystemReadyResponse,
)

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness check - is the service running?"""
    return HealthResponse(
        status="healthy",
        version=__version__,
        timestamp=datetime.now(UTC),
    )


@router.get("/health/config", response_model=SystemConfigResponse)
async def system_config() -> SystemConfigResponse:
    """Report whether the system has LLM provider keys configured.

    This is unauthenticated so the frontend can show a setup-required
    screen before asking users to log in.
    """
    settings = get_settings()
    paid = settings.deployment_providers
    return SystemConfigResponse(
        chat_provider=settings.pathfinder_chat_provider,
        llm_configured=bool(paid),
        providers=ProviderStatus(
            openai="openai" in paid,
            anthropic="anthropic" in paid,
            google="google" in paid,
            ollama="ollama" in paid,
        ),
    )


@router.get("/health/system", response_model=SystemReadyResponse)
async def system_ready() -> SystemReadyResponse:
    """Aggregate readiness for the UI startup gate: API subsystems + worker.

    Always returns 200 so the frontend can poll a single endpoint and read
    ``ready`` to decide whether to show the startup loader. Unlike
    ``/health/ready`` (the API container's own healthcheck), worker liveness
    is included here - the worker is a sibling process, so its death must not
    flip the API's container health.
    """
    state = get_readiness()
    worker_alive = False

    try:
        async with async_session_factory() as session:
            await check_database(session)
            worker_alive = await worker_is_alive(session)
        state.mark_ready("database")
    except Exception as e:
        logger.exception("System readiness: database unreachable")
        state.mark_failed("database", str(e) or type(e).__name__)

    api_ready = state.all_ready
    not_ready = list(state.not_ready)
    if not worker_alive:
        not_ready.append("worker")

    return SystemReadyResponse(
        ready=api_ready and worker_alive,
        api_ready=api_ready,
        worker_alive=worker_alive,
        not_ready=not_ready,
        degraded=state.degraded,
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness_check() -> ReadinessResponse | JSONResponse:
    """Readiness check - can this process serve requests?

    Returns 503 until every process subsystem is ready (database, embedding
    model, graph checkpointer, and input screening where the deployment runs
    it) and at least one site catalog is loaded.
    ``degraded`` names the sites whose catalog is not loaded; they are refused
    on their own routes and retried in the background. Also
    re-verifies the DB with a live ping so stale state does not mask a broken
    dependency.
    """
    state = get_readiness()

    try:
        async with async_session_factory() as session:
            await check_database(session)
        state.mark_ready("database")
    except Exception as e:
        logger.exception("Readiness check: database unreachable")
        state.mark_failed("database", str(e) or type(e).__name__)

    ready = state.all_ready
    response = ReadinessResponse(
        status="healthy" if ready else "unhealthy",
        version=__version__,
        timestamp=datetime.now(UTC),
        readiness=state,
        not_ready=state.not_ready,
        degraded=state.degraded,
    )
    if not ready:
        return JSONResponse(
            status_code=503,
            content=response.model_dump(mode="json", by_alias=True),
        )
    return response
