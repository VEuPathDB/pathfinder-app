"""Tests for observability setup."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.instrumentation.httpx import (
    HTTPX2ClientInstrumentor,
    HTTPXClientInstrumentor,
)

from pathfinder.platform import observability
from pathfinder.platform.observability import (
    _build_resource,
    _configure_exporters,
    _configure_log_export,
    _instrument_agents,
    _instrument_http_clients,
    setup_observability,
    shutdown_observability,
)


def test_setup_observability_noop_without_config() -> None:
    """No-ops when neither SigNoz nor Langfuse is configured."""
    mock_settings = MagicMock(
        signoz_otel_endpoint=None,
        signoz_trace_otel_http_endpoint=None,
        langfuse_secret_key="",
    )
    with (
        patch(
            "pathfinder.platform.observability.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "pathfinder.platform.observability.trace.set_tracer_provider",
        ) as set_provider,
    ):
        setup_observability(app=MagicMock(), db_engine=MagicMock())

    assert set_provider.call_count == 0


def test_configure_log_export_noop_without_signoz() -> None:
    """Log export is not configured when SigNoz is disabled."""
    mock_settings = MagicMock(signoz_otel_endpoint=None)
    root = logging.getLogger()
    handler_count_before = len(root.handlers)
    with patch(
        "pathfinder.platform.observability.get_settings",
        return_value=mock_settings,
    ):
        _configure_log_export()
    assert len(root.handlers) == handler_count_before


def test_shutdown_observability_flushes_stored_provider() -> None:
    """shutdown_observability calls shutdown on the stored provider reference."""
    mock_provider = MagicMock()
    original = observability._otel.provider
    observability._otel.provider = mock_provider
    try:
        shutdown_observability()
        assert mock_provider.shutdown.call_count == 1
        assert observability._otel.provider is None
    finally:
        observability._otel.provider = original


def test_shutdown_observability_noop_when_no_provider() -> None:
    """shutdown_observability no-ops when no provider was configured."""
    original = observability._otel.provider
    observability._otel.provider = None
    try:
        shutdown_observability()
        assert (observability._otel.provider, observability._otel.meter_provider) == (
            None,
            None,
        )
    finally:
        observability._otel.provider = original


def test_configure_log_export_attaches_handler_with_signoz() -> None:
    """OTLP log handler is attached to root logger when SigNoz is enabled."""
    mock_settings = MagicMock(signoz_otel_endpoint="http://localhost:4317")
    root = logging.getLogger()
    handler_count_before = len(root.handlers)
    with (
        patch(
            "pathfinder.platform.observability.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "pathfinder.platform.observability.GrpcLogExporter",
        ),
        patch(
            "pathfinder.platform.observability.BatchLogRecordProcessor",
        ),
    ):
        _configure_log_export()
    assert len(root.handlers) == handler_count_before + 1
    # Remove the handler this test added.
    root.handlers.pop()


def test_shutdown_observability_flushes_meter_provider() -> None:
    """shutdown_observability calls shutdown on the stored meter provider."""
    mock_meter = MagicMock()
    original = observability._otel.meter_provider
    observability._otel.meter_provider = mock_meter
    try:
        shutdown_observability()
        assert mock_meter.shutdown.call_count == 1
        assert observability._otel.meter_provider is None
    finally:
        observability._otel.meter_provider = original


def test_resource_includes_enriched_attributes() -> None:
    """Resource includes service.version and deployment.environment.name."""
    mock_settings = MagicMock(api_env="production")
    with patch(
        "pathfinder.platform.observability.get_settings",
        return_value=mock_settings,
    ):
        resource = _build_resource()
    attrs = dict(resource.attributes)
    assert attrs["service.name"] == "pathfinder-api"
    assert "service.version" in attrs
    assert attrs["deployment.environment.name"] == "production"
    assert "service.instance.id" in attrs


def test_configure_exporters_returns_provider_for_langfuse_only() -> None:
    """Langfuse-only setup gets a TracerProvider; SDK attaches its own processor."""
    mock_settings = MagicMock(
        signoz_otel_endpoint=None,
        signoz_trace_otel_http_endpoint=None,
        langfuse_host="http://langfuse:3000",
        langfuse_public_key="pk-lf-test",
        langfuse_secret_key="sk-lf-test",
        api_env="development",
    )

    with (
        patch(
            "pathfinder.platform.observability.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "pathfinder.platform.observability.HttpSpanExporter",
        ) as exporter_cls,
    ):
        provider = _configure_exporters()

    assert provider is not None
    assert exporter_cls.call_count == 0


def test_setup_observability_triggers_langfuse_sdk_when_key_set() -> None:
    """Setup starts the Langfuse SDK when Langfuse is configured. The SDK attaches
    its own span processor and owns the export."""
    mock_settings = MagicMock(
        signoz_otel_endpoint=None,
        signoz_trace_otel_http_endpoint=None,
        langfuse_host="http://langfuse:3000",
        langfuse_public_key="pk-lf-test",
        langfuse_secret_key="sk-lf-test",
        api_env="development",
    )

    with (
        patch(
            "pathfinder.platform.observability.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "pathfinder.platform.observability.get_langfuse",
        ) as get_langfuse_mock,
        patch(
            "pathfinder.platform.observability.trace.set_tracer_provider",
        ),
        patch(
            "pathfinder.platform.observability._instrument_fastapi",
        ),
        patch(
            "pathfinder.platform.observability._instrument_database",
        ),
        patch(
            "pathfinder.platform.observability._instrument_http_clients",
        ),
        patch(
            "pathfinder.platform.observability._instrument_agents",
        ),
    ):
        setup_observability(app=MagicMock(), db_engine=MagicMock())

    assert get_langfuse_mock.call_count == 1


def test_setup_observability_skips_langfuse_sdk_when_key_absent() -> None:
    """Langfuse SDK init is skipped when no secret key is set (SigNoz only)."""
    mock_settings = MagicMock(
        signoz_otel_endpoint=None,
        signoz_trace_otel_http_endpoint="http://signoz:4318/v1/traces",
        langfuse_host="",
        langfuse_public_key="",
        langfuse_secret_key="",
        api_env="development",
    )

    with (
        patch(
            "pathfinder.platform.observability.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "pathfinder.platform.observability.get_langfuse",
        ) as get_langfuse_mock,
        patch(
            "pathfinder.platform.observability.trace.set_tracer_provider",
        ),
        patch(
            "pathfinder.platform.observability._instrument_fastapi",
        ),
        patch(
            "pathfinder.platform.observability._instrument_database",
        ),
        patch(
            "pathfinder.platform.observability._instrument_http_clients",
        ),
        patch(
            "pathfinder.platform.observability._instrument_agents",
        ),
    ):
        setup_observability(app=MagicMock(), db_engine=MagicMock())

    assert get_langfuse_mock.call_count == 0


def test_configure_exporters_prefers_signoz_http_for_traces_when_configured() -> None:
    """SigNoz traces can use a dedicated OTLP/HTTP endpoint."""
    mock_settings = MagicMock(
        signoz_otel_endpoint="http://localhost:4317",
        signoz_trace_otel_http_endpoint="http://localhost:4318/v1/traces",
        langfuse_host="",
        langfuse_public_key="",
        langfuse_secret_key="",
        api_env="development",
    )
    mock_exporter = MagicMock()
    mock_processor = MagicMock()

    with (
        patch(
            "pathfinder.platform.observability.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "pathfinder.platform.observability.HttpSpanExporter",
            return_value=mock_exporter,
        ) as http_exporter_cls,
        patch(
            "pathfinder.platform.observability.BatchSpanProcessor",
            return_value=mock_processor,
        ),
    ):
        provider = _configure_exporters()

    assert provider is not None
    assert http_exporter_cls.call_count == 1
    assert http_exporter_cls.call_args.kwargs == {
        "endpoint": "http://localhost:4318/v1/traces"
    }


def test_both_httpx_distributions_are_instrumented() -> None:
    """The model providers speak httpx2, the WDK client httpx.

    A span is lost for every client the setup leaves uninstrumented.
    """
    httpx_one = HTTPXClientInstrumentor()
    httpx_two = HTTPX2ClientInstrumentor()
    try:
        _instrument_http_clients()
        instrumented = (
            httpx_one.is_instrumented_by_opentelemetry,
            httpx_two.is_instrumented_by_opentelemetry,
        )
    finally:
        httpx_one.uninstrument()
        httpx_two.uninstrument()

    assert instrumented == (True, True)


@pytest.mark.parametrize("include_content", [True, False])
def test_instrument_agents_follows_include_content_setting(
    include_content: bool,
) -> None:
    """Prompt and completion export follows OTEL_INCLUDE_CONTENT."""
    mock_settings = MagicMock(otel_include_content=include_content)
    with (
        patch(
            "pathfinder.platform.observability.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "pathfinder.platform.observability.Agent.instrument_all",
        ) as instrument_all,
    ):
        _instrument_agents()

    (instrumentation,) = instrument_all.call_args.args
    assert instrumentation.include_content is include_content
