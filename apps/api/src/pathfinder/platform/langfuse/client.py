"""Lazy Langfuse SDK singleton. Returns None when credentials are absent."""

import threading
from dataclasses import dataclass

from assistant_core.platform.logging import get_logger
from langfuse import Langfuse
from langfuse.span_filter import is_default_export_span
from opentelemetry.sdk.trace import ReadableSpan

from pathfinder.platform.config import get_settings

logger = get_logger(__name__)


@dataclass
class _Singleton:
    """The client this process built, and whether it tried to build one."""

    client: Langfuse | None = None
    initialized: bool = False


_state = _Singleton()
_lock = threading.Lock()


def _should_export_span(span: ReadableSpan) -> bool:
    """Langfuse export filter that also accepts pathfinder app spans.

    Langfuse's default filter (``is_default_export_span``) only keeps spans
    from known LLM instrumentors or spans with ``gen_ai.*`` attributes. Our
    turn-level span (``chat.turn``) is created by the ``pathfinder.pipeline``
    tracer and carries only ``langfuse.*`` / ``app.*`` attributes, so the
    default filter drops it and its root-trace metadata never reaches
    Langfuse. Accept any span that explicitly sets ``langfuse.*`` attributes.
    """
    if is_default_export_span(span):
        return True
    return any(key.startswith("langfuse.") for key in (span.attributes or {}))


def get_langfuse() -> Langfuse | None:
    """Return the Langfuse SDK client, or None when not configured.

    Thread-safe lazy initialization. The client is created once and reused.
    """
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
            should_export_span=_should_export_span,
        )
        _state.initialized = True
        logger.info("Langfuse SDK initialized", host=settings.langfuse_host)
        return _state.client


def shutdown_langfuse() -> None:
    """Flush and shutdown the Langfuse client. Called during app shutdown."""
    if _state.client is not None:
        _state.client.shutdown()
        _state.client = None
    _state.initialized = False
