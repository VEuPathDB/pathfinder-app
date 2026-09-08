"""OTEL tracing, metrics, and logs, plus library instrumentation.

The TracerProvider here must be installed before ``get_langfuse()`` runs,
because OTEL accepts a provider only once.
"""

import logging
from importlib.metadata import PackageNotFoundError, version
from uuid import uuid4

from assistant_core.platform.context import request_id_ctx, site_id_ctx, user_id_ctx
from assistant_core.platform.logging import get_logger
from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter as GrpcLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as GrpcSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HttpSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import (
    HTTPX2ClientInstrumentor,
    HTTPXClientInstrumentor,
)
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic_ai import Agent, InstrumentationSettings

from pathfinder.platform.config import get_settings
from pathfinder.platform.langfuse.client import get_langfuse

logger = get_logger(__name__)


class _OtelState:
    """Module-level mutable state for the OTEL providers."""

    provider: TracerProvider | None = None
    meter_provider: MeterProvider | None = None


_otel = _OtelState()


def _get_version() -> str:
    """Read the package version from installed metadata."""
    try:
        return version("pathfinder-api")
    except PackageNotFoundError:
        return "0.0.0-dev"


def get_observability_identity() -> dict[str, str]:
    """Return stable service identity fields shared across traces and spans."""
    settings = get_settings()
    return {
        "service.name": "pathfinder-api",
        "service.version": _get_version(),
        "deployment.environment.name": settings.api_env,
    }


def _build_resource() -> Resource:
    """Build the OTEL Resource with enriched semantic convention attributes."""
    return Resource.create(
        {
            **get_observability_identity(),
            "service.instance.id": str(uuid4()),
        }
    )


def _configure_exporters() -> TracerProvider | None:
    """Create a TracerProvider with SigNoz trace export wired in.

    Returns None when neither SigNoz nor Langfuse is configured. Langfuse alone
    still gets a provider, so its span processor attaches to this resource.
    """
    settings = get_settings()
    has_signoz_trace = bool(
        settings.signoz_trace_otel_http_endpoint or settings.signoz_otel_endpoint
    )
    has_langfuse = bool(settings.langfuse_secret_key)
    if not has_signoz_trace and not has_langfuse:
        return None

    provider = TracerProvider(resource=_build_resource())

    if settings.signoz_trace_otel_http_endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(
                HttpSpanExporter(endpoint=settings.signoz_trace_otel_http_endpoint)
            )
        )
        logger.info(
            "OTEL exporter: SigNoz traces",
            endpoint=settings.signoz_trace_otel_http_endpoint,
            transport="http",
        )
    elif settings.signoz_otel_endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(
                GrpcSpanExporter(
                    endpoint=settings.signoz_otel_endpoint,
                    insecure=True,
                )
            )
        )
        logger.info(
            "OTEL exporter: SigNoz traces",
            endpoint=settings.signoz_otel_endpoint,
            transport="grpc",
        )

    _otel.provider = provider
    return provider


def _configure_metrics_export(resource: Resource) -> None:
    """Create a MeterProvider with a SigNoz gRPC exporter.

    Does nothing when SigNoz is not configured. Langfuse does not accept OTEL
    metrics.
    """
    settings = get_settings()
    if not settings.signoz_otel_endpoint:
        return

    exporter = OTLPMetricExporter(
        endpoint=settings.signoz_otel_endpoint,
        insecure=True,
    )
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=15_000)
    _otel.meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(_otel.meter_provider)
    logger.info("OTEL metrics: SigNoz", endpoint=settings.signoz_otel_endpoint)


def _configure_log_export() -> None:
    """Attach an OTLP log handler to the root logger for SigNoz.

    Does nothing when SigNoz is not configured. The stdout handler stays in
    place, so logs go to both places.
    """
    settings = get_settings()
    if not settings.signoz_otel_endpoint:
        return

    log_exporter = GrpcLogExporter(
        endpoint=settings.signoz_otel_endpoint,
        insecure=True,
    )
    log_provider = LoggerProvider(resource=_build_resource())
    log_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    set_logger_provider(log_provider)

    handler = LoggingHandler(level=logging.DEBUG, logger_provider=log_provider)
    logging.getLogger().addHandler(handler)
    logger.info("OTLP log export: SigNoz", endpoint=settings.signoz_otel_endpoint)


def _instrument_fastapi(app: FastAPI) -> None:
    """Instrument FastAPI with per-request spans."""

    def server_request_hook(span: trace.Span, scope: dict[str, object]) -> None:
        if not span.is_recording():
            return
        uid = user_id_ctx.get()
        if uid is not None:
            span.set_attribute("app.user_id", str(uid))
        sid = site_id_ctx.get()
        if sid is not None:
            span.set_attribute("app.site_id", sid)
        rid = request_id_ctx.get()
        if rid is not None:
            span.set_attribute("app.request_id", rid)

    FastAPIInstrumentor.instrument_app(
        app,
        server_request_hook=server_request_hook,
        excluded_urls="health",
    )
    logger.info("Instrumented: FastAPI")


def _instrument_database(db_engine: object) -> None:
    """Instrument SQLAlchemy with per-query spans."""
    sync_engine = getattr(db_engine, "sync_engine", db_engine)
    SQLAlchemyInstrumentor().instrument(engine=sync_engine)
    logger.info("Instrumented: SQLAlchemy")


def _instrument_http_clients() -> None:
    """Instrument both httpx distributions with per-outgoing-request spans.

    The model providers speak httpx2 and the WDK client speaks httpx.
    """
    HTTPXClientInstrumentor().instrument()
    HTTPX2ClientInstrumentor().instrument()
    logger.info("Instrumented: httpx, httpx2")


def _instrument_agents() -> None:
    """Instrument pydantic-ai agents with per-run/model/tool spans."""
    include_content = get_settings().otel_include_content
    Agent.instrument_all(InstrumentationSettings(include_content=include_content))
    logger.info("Instrumented: pydantic-ai agents", include_content=include_content)


def setup_observability(
    *,
    app: FastAPI | None = None,
    db_engine: object | None = None,
) -> None:
    """Configure OTEL exporters and library instrumentation.

    Does nothing when neither SigNoz nor Langfuse is configured. Callers must
    invoke this before any path that initializes the Langfuse SDK.
    """
    provider = _configure_exporters()
    if provider is None:
        logger.info("Observability disabled (no SIGNOZ or LANGFUSE configured)")
        return

    trace.set_tracer_provider(provider)
    _configure_metrics_export(provider.resource)
    _configure_log_export()

    # Langfuse reuses an installed provider, so its init must follow
    # ``set_tracer_provider``.
    if get_settings().langfuse_secret_key:
        get_langfuse()

    if app is not None:
        _instrument_fastapi(app)
    if db_engine is not None:
        _instrument_database(db_engine)
    _instrument_http_clients()
    _instrument_agents()


def shutdown_observability() -> None:
    """Flush and shut down the OTEL providers."""
    if _otel.meter_provider is not None:
        _otel.meter_provider.shutdown()
        _otel.meter_provider = None
    if _otel.provider is not None:
        _otel.provider.shutdown()
        _otel.provider = None
    logger.info("OTEL providers shut down")
