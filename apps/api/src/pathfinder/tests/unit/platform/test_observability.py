"""Each process installs the runtime's tracer under its own service name."""

from __future__ import annotations

import base64
from typing import Any

import pytest
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from pathfinder import __version__
from pathfinder.platform import observability
from pathfinder.platform.config import get_settings


def _recorded_install(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def install(**kwargs: Any) -> bool:
        calls.append(kwargs)
        return True

    monkeypatch.setattr(observability, "install_observability", install)
    return calls


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _fresh_settings() -> Any:
    yield
    get_settings.cache_clear()


def test_the_worker_installs_under_its_own_name_with_the_langfuse_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings(
        monkeypatch,
        LANGFUSE_HOST="http://langfuse:3000",
        LANGFUSE_PUBLIC_KEY="pk-lf-test",
        LANGFUSE_SECRET_KEY="sk-lf-test",
        OTEL_INCLUDE_CONTENT="true",
    )
    calls = _recorded_install(monkeypatch)

    observability.setup_observability(service_name="pathfinder-worker")

    expected = base64.b64encode(b"pk-lf-test:sk-lf-test").decode()
    assert calls == [
        {
            "service_name": "pathfinder-worker",
            "service_version": __version__,
            "environment": get_settings().api_env,
            "include_content": True,
            "exporter_headers": {"Authorization": f"Basic {expected}"},
            "engine": None,
        }
    ]


def test_without_langfuse_keys_no_header_is_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings(
        monkeypatch, LANGFUSE_HOST="", LANGFUSE_PUBLIC_KEY="", LANGFUSE_SECRET_KEY=""
    )
    calls = _recorded_install(monkeypatch)

    observability.setup_observability(service_name="pathfinder-api")

    assert [call["exporter_headers"] for call in calls] == [{}]


def test_a_route_is_one_span_without_its_stream_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A streamed route sends one message per chunk; the request stays one span."""
    seen: dict[str, Any] = {}

    def _instrument(app: FastAPI, **kwargs: Any) -> None:
        seen["app"] = app
        seen.update(kwargs)

    monkeypatch.setattr(FastAPIInstrumentor, "instrument_app", _instrument)
    app = FastAPI()

    observability.trace_routes(app)

    assert seen == {
        "app": app,
        "excluded_urls": "health",
        "exclude_spans": ["receive", "send"],
    }
