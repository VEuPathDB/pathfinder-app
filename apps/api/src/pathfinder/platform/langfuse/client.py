"""Lazy Langfuse SDK singleton. Returns None when credentials are absent.

The client exports only its own events, on a tracer provider of its own; the
process's traces reach Langfuse through the OTLP exporter.
"""

import threading
from dataclasses import dataclass

from assistant_core.platform.logging import get_logger
from langfuse import Langfuse
from opentelemetry.sdk.trace import TracerProvider

from pathfinder.platform.config import get_settings

logger = get_logger(__name__)


@dataclass
class _Singleton:
    """The client this process built, and whether it tried to build one."""

    client: Langfuse | None = None
    initialized: bool = False


_state = _Singleton()
_lock = threading.Lock()


def get_langfuse() -> Langfuse | None:
    """Return the Langfuse SDK client, or None when not configured."""
    if _state.initialized:
        return _state.client

    with _lock:
        if _state.initialized:
            return _state.client

        settings = get_settings()
        if not settings.langfuse_secret_key:
            logger.info("Langfuse SDK disabled (no LANGFUSE_SECRET_KEY)")
            _state.initialized = True
            return None

        _state.client = Langfuse(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_host,
            environment=settings.api_env,
            tracer_provider=TracerProvider(),
        )
        _state.initialized = True
        logger.info("Langfuse SDK initialized", host=settings.langfuse_host)
        return _state.client


def shutdown_langfuse() -> None:
    """Flush and shut down the Langfuse client."""
    if _state.client is not None:
        _state.client.shutdown()
        _state.client = None
    _state.initialized = False
