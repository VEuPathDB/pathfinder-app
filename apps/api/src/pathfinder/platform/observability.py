"""This deployment's identity for the runtime's tracer, and the Langfuse ingress header.

The API and the worker each call ``setup_observability`` once at start. Only the
API passes its engine, and its routes are traced from ``create_app``.
"""

import base64

from assistant_core.platform.observability import install_observability
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from sqlalchemy.ext.asyncio import AsyncEngine

from pathfinder import __version__
from pathfinder.platform.config import Settings, get_settings


def langfuse_ingress_headers(settings: Settings) -> dict[str, str]:
    """The basic-auth header Langfuse's OTLP ingress reads, built from the project keys."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return {}
    pair = f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}"
    return {"Authorization": f"Basic {base64.b64encode(pair.encode()).decode()}"}


def trace_routes(app: FastAPI) -> None:
    """Open one server span per request on the process's tracer.

    The spans are no-ops until ``setup_observability`` installs a provider.
    """
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health")


def setup_observability(
    *,
    service_name: str,
    engine: AsyncEngine | None = None,
) -> None:
    """Export this process's traces where ``OTEL_EXPORTER_OTLP_ENDPOINT`` points."""
    settings = get_settings()
    install_observability(
        service_name=service_name,
        service_version=__version__,
        environment=settings.api_env,
        include_content=settings.otel_include_content,
        exporter_headers=langfuse_ingress_headers(settings),
        engine=engine,
    )
