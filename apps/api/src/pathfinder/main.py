"""FastAPI application entrypoint."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import uuid4

from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.embeddings.embedder import (
    EmbeddingUnavailableError,
    get_embedder,
)
from assistant_core.memory.lifespan import lifespan_memory_store
from assistant_core.platform.context import request_id_ctx
from assistant_core.platform.db import async_session_factory, close_db, get_engine
from assistant_core.platform.logging import get_logger, setup_logging
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.strategy.operations.apply import ApplyError
from veupathdb.eda.factory import close_all_eda_clients
from veupathdb.errors import VEuPathDBError
from veupathdb.observability.otel import OpenTelemetryObserver
from veupathdb.observer import set_observer
from veupathdb.wdk.factory import close_all_clients
from veupathdb.wdk.site_router import get_site_router
from veupathdb_mcp.catalog.discovery_service import (
    get_discovery_service,
)
from veupathdb_mcp.embeddings.db import use_embedding_session_factory

from pathfinder import __version__
from pathfinder.ai.capabilities.security import warm_up_scanner
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.platform.config import get_settings
from pathfinder.platform.context import request_base_url_ctx
from pathfinder.platform.error_handlers import (
    apply_error_handler,
    http_exception_handler,
    rate_limit_handler,
    request_validation_handler,
    veupathdb_error_handler,
)
from pathfinder.platform.migrations import init_db
from pathfinder.platform.observability import (
    setup_observability,
    shutdown_observability,
)
from pathfinder.platform.principal import SERVICE_AUTH_HEADER
from pathfinder.platform.readiness import get_readiness, reset_readiness
from pathfinder.platform.security import (
    RejectNullBytesMiddleware,
    csrf_middleware,
    limiter,
)
from pathfinder.platform.site_catalogs import (
    preload_catalogs,
    run_catalog_retry_loop,
)
from pathfinder.services.eda.catalog import preload_study_index
from pathfinder.transport.http.openapi import install_openapi_post_passes
from pathfinder.transport.http.routers import (
    chat,
    control_sets,
    conversations,
    dev,
    eda,
    evaluation,
    experiments,
    exports,
    feedback,
    gene_sets,
    health,
    me,
    memories,
    models,
    sites,
    tasks,
    tiers,
    user_data,
    veupathdb_auth,
)

logger = get_logger(__name__)


async def _warm_up_subsystems() -> None:
    """Reach the embedding backend, load PIGuard, and preload the catalogs.

    Each step is independent. A failure marks its subsystem as not ready and
    the rest continue. The PIGuard load holds the CPU for seconds, so it runs
    on a thread and the server keeps answering while it runs.
    """
    readiness = get_readiness()
    try:
        logger.info("[warm-up] Reaching the embedding backend")
        await get_embedder().embed_query("ready")
        readiness.mark_ready("embedding_backend")
    except (
        EmbeddingUnavailableError,
        VEuPathDBError,
        OSError,
        RuntimeError,
        ValueError,
    ) as e:
        logger.exception("[warm-up] Embedding backend failed")
        readiness.mark_failed("embedding_backend", str(e))

    if get_settings().piguard_enabled:
        try:
            logger.info("[warm-up] Loading PIGuard ONNX model")
            await asyncio.to_thread(warm_up_scanner)
            readiness.mark_ready("piguard")
        except (VEuPathDBError, OSError, RuntimeError) as e:
            logger.exception("[warm-up] PIGuard failed")
            readiness.mark_failed("piguard", str(e))
    else:
        logger.info("[warm-up] PIGuard disabled (PIGUARD_ENABLED=false); skipping")
        readiness.mark_ready("piguard")

    try:
        logger.info("[warm-up] Preloading discovery catalogs (all sites)")
        # One catalog builds at a time, so the slow portals go last and a
        # component site's budget is not spent waiting behind them.
        sites = sorted(
            get_site_router().list_sites(), key=lambda site: (site.is_portal, site.id)
        )
        await preload_catalogs(
            loader=get_discovery_service().get_catalog,
            site_ids=[site.id for site in sites],
            readiness=readiness,
            budget_seconds=get_settings().site_preload_timeout_seconds,
        )
    except VEuPathDBError, OSError, RuntimeError:
        logger.exception("[warm-up] Discovery preload raised")

    try:
        logger.info("[warm-up] Syncing the EDA study index")
        await preload_study_index()
    except VEuPathDBError, OSError, RuntimeError:
        logger.exception("[warm-up] EDA study index sync raised")


def _report_warm_up_death(task: asyncio.Task[Any]) -> None:
    """Fail every loading subsystem when the warm-up dies past its handlers."""
    if task.cancelled():
        return
    error = task.exception()
    if error is None:
        return
    logger.error("[warm-up] Warm-up task died", exc_info=error)
    get_readiness().fail_loading(error)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler."""
    settings = get_settings()
    setup_logging()
    from pathfinder.jobs.logging_filters import (  # noqa: PLC0415
        install_procrastinate_redaction,
    )

    install_procrastinate_redaction()
    logger.info("Starting Pathfinder API", version=__version__, env=settings.api_env)

    readiness = get_readiness()
    # The index shares this process's pool instead of opening a second one.
    use_embedding_session_factory(async_session_factory)

    try:
        await init_db()
        readiness.mark_ready("database")
    except (VEuPathDBError, OSError, RuntimeError) as e:
        readiness.mark_failed("database", str(e))
        raise

    # Observability and the prompt seed both need a ready database.
    setup_observability(app=app, db_engine=get_engine())
    set_observer(OpenTelemetryObserver())
    from pathfinder.platform.langfuse.prompts import seed_prompts  # noqa: PLC0415

    seed_prompts()

    from pathfinder.jobs.app import procrastinate_app  # noqa: PLC0415
    from pathfinder.platform.tasks import spawn  # noqa: PLC0415

    # uvicorn binds only after this handler yields, so the warm-up runs beside
    # the server and ``/health/ready`` reports which catalogs are still loading.
    warm_up = spawn(_warm_up_subsystems(), name="warm-up")
    if warm_up is not None:
        warm_up.add_done_callback(_report_warm_up_death)

    catalog_retry = spawn(
        run_catalog_retry_loop(
            loader=get_discovery_service().get_catalog,
            readiness=readiness,
            budget_seconds=settings.site_preload_timeout_seconds,
            interval_seconds=settings.site_retry_interval_seconds,
        ),
        name="catalog-retry",
    )

    # The API process never runs a turn; it opens the checkpointer so the
    # tables exist before the worker writes them.
    async with (
        lifespan_checkpointer(
            settings.database_url,
            checkpoint_types=get_assistant_registry().checkpoint_types(),
        ),
        lifespan_memory_store(settings.database_url) as memory_store,
        procrastinate_app.open_async(),
    ):
        app.state.memory_store = memory_store
        readiness.mark_ready("graph_checkpointer")

        from pathfinder.services.export.sweeper import (  # noqa: PLC0415
            run_sweeper_loop,
        )

        export_sweeper_task = spawn(run_sweeper_loop(), name="export-sweeper")

        yield

        logger.info("Shutting down Pathfinder API")

        if export_sweeper_task is not None:
            export_sweeper_task.cancel()
        if warm_up is not None:
            warm_up.cancel()
        if catalog_retry is not None:
            catalog_retry.cancel()

    reset_readiness()
    await close_all_clients()
    await close_all_eda_clients()
    await close_db()
    shutdown_observability()
    from pathfinder.platform.langfuse.client import (  # noqa: PLC0415
        shutdown_langfuse,
    )

    shutdown_langfuse()


def _register_routers(app: FastAPI) -> None:
    """Mount every always-on HTTP router."""
    for router in (
        health.router,
        sites.router,
        models.router,
        tiers.router,
        chat.router,
        conversations.router,
        experiments.router,
        control_sets.router,
        eda.router,
        veupathdb_auth.router,
        gene_sets.router,
        exports.router,
        feedback.router,
        user_data.router,
        evaluation.router,
        memories.router,
        me.router,
        tasks.router,
    ):
        app.include_router(router)


def create_app(*, include_dev_routes: bool | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    ``include_dev_routes=None`` follows the process settings; ``False`` pins
    the production route set, whatever the environment.
    """
    settings = get_settings()

    app = FastAPI(
        title="Pathfinder API",
        description="VEuPathDB Strategy Builder Chatbot API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.api_docs_enabled else None,
        redoc_url="/redoc" if settings.api_docs_enabled else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            SERVICE_AUTH_HEADER,
            "X-Request-ID",
            "X-Requested-With",
            "X-VEUPATHDB-AUTH",
            "X-VEUPATHDB-AUTHORIZATION",
        ],
    )

    app.state.limiter = limiter

    # The CSRF middleware registers after CORS, so a preflight request passes
    # through it.
    app.middleware("http")(csrf_middleware)

    # PostgreSQL text cannot hold a NUL byte, so a NUL is a 422 and not a 500.
    app.add_middleware(RejectNullBytesMiddleware)

    @app.middleware("http")
    async def add_request_id(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        request_id_ctx.set(request_id)
        veupathdb_auth_token_ctx.set(
            request.headers.get("X-VEUPATHDB-AUTH")
            or request.headers.get("X-VEUPATHDB-AUTHORIZATION")
            or request.cookies.get("Authorization")
        )
        # A full download URL needs the frontend origin.
        origin = (
            request.headers.get("Origin")
            or request.headers.get("Referer", "").rstrip("/").rsplit("/api/", 1)[0]
            or (settings.cors_origins[0] if settings.cors_origins else None)
        )
        request_base_url_ctx.set(origin)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    for exc_type, handler in (
        (VEuPathDBError, veupathdb_error_handler),
        (ApplyError, apply_error_handler),
        (HTTPException, http_exception_handler),
        (RateLimitExceeded, rate_limit_handler),
        (RequestValidationError, request_validation_handler),
    ):
        app.add_exception_handler(
            exc_type,
            cast("Callable[[Request, Exception], Awaitable[Response]]", handler),
        )

    _register_routers(app)

    # The dev routes mount under the mock chat provider only.
    if include_dev_routes is None:
        include_dev_routes = settings.pathfinder_chat_provider.strip().lower() == "mock"
    if include_dev_routes:
        app.include_router(dev.router)

    install_openapi_post_passes(app)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "pathfinder.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=bool(settings.is_development),
    )
