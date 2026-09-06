"""What ``classify_error`` makes of each failure a tool can raise."""

from __future__ import annotations

import httpx
from veupathdb.errors import ValidationError, WDKError

from pathfinder.ai.capabilities.error_classification import (
    ErrorCategory,
    classify_error,
)
from pathfinder.platform.errors import AppError, ErrorCode, InternalError, NotFoundError


class TestClassifyWDKError:
    """WDKError classification depends on HTTP status code."""

    def test_wdk_500_is_transient(self) -> None:
        assert (
            classify_error(WDKError("server blew up", status=500))
            == ErrorCategory.TRANSIENT
        )

    def test_wdk_502_is_transient(self) -> None:
        assert (
            classify_error(WDKError("bad gateway", status=502))
            == ErrorCategory.TRANSIENT
        )

    def test_wdk_503_is_transient(self) -> None:
        assert (
            classify_error(WDKError("service unavailable", status=503))
            == ErrorCategory.TRANSIENT
        )

    def test_wdk_400_is_semantic(self) -> None:
        assert (
            classify_error(WDKError("bad request", status=400))
            == ErrorCategory.SEMANTIC
        )

    def test_wdk_404_is_semantic(self) -> None:
        assert (
            classify_error(WDKError("not found", status=404)) == ErrorCategory.SEMANTIC
        )

    def test_wdk_422_is_semantic(self) -> None:
        assert (
            classify_error(WDKError("unprocessable", status=422))
            == ErrorCategory.SEMANTIC
        )

    def test_wdk_499_is_semantic(self) -> None:
        assert (
            classify_error(WDKError("client error", status=499))
            == ErrorCategory.SEMANTIC
        )


class TestClassifyHttpxErrors:
    """httpx network errors are TRANSIENT."""

    def test_timeout_exception_is_transient(self) -> None:
        exc = httpx.TimeoutException("timed out")
        assert classify_error(exc) == ErrorCategory.TRANSIENT

    def test_connect_error_is_transient(self) -> None:
        exc = httpx.ConnectError("connection refused")
        assert classify_error(exc) == ErrorCategory.TRANSIENT


class TestClassifyOSErrors:
    """OSError and subclasses are TRANSIENT."""

    def test_os_error_is_transient(self) -> None:
        assert classify_error(OSError("file not found")) == ErrorCategory.TRANSIENT

    def test_connection_refused_error_is_transient(self) -> None:
        assert (
            classify_error(ConnectionRefusedError("refused")) == ErrorCategory.TRANSIENT
        )

    def test_connection_error_is_transient(self) -> None:
        assert classify_error(ConnectionError("reset")) == ErrorCategory.TRANSIENT


class TestClassifyAppErrors:
    """AppError and its subclasses are SEMANTIC."""

    def test_not_found_error_is_semantic(self) -> None:
        assert classify_error(NotFoundError()) == ErrorCategory.SEMANTIC

    def test_validation_error_is_semantic(self) -> None:
        assert classify_error(ValidationError()) == ErrorCategory.SEMANTIC

    def test_generic_app_error_is_semantic(self) -> None:
        err = AppError(
            code=ErrorCode.INTERNAL_ERROR,
            title="Something went wrong",
            status=400,
        )
        assert classify_error(err) == ErrorCategory.SEMANTIC

    def test_app_error_with_500_status_is_still_semantic(self) -> None:
        """AppError classification uses the type, not the HTTP status."""
        assert classify_error(InternalError()) == ErrorCategory.SEMANTIC


class TestClassifyRuntimeErrorPermanent:
    """A RuntimeError with a config or availability message is PERMANENT."""

    def test_not_configured_is_permanent(self) -> None:
        assert (
            classify_error(RuntimeError("service not configured"))
            == ErrorCategory.PERMANENT
        )

    def test_not_available_is_permanent(self) -> None:
        assert (
            classify_error(RuntimeError("feature not available"))
            == ErrorCategory.PERMANENT
        )

    def test_not_enabled_is_permanent(self) -> None:
        assert (
            classify_error(RuntimeError("tool not enabled")) == ErrorCategory.PERMANENT
        )

    def test_service_is_disabled_is_permanent(self) -> None:
        assert (
            classify_error(RuntimeError("service is disabled"))
            == ErrorCategory.PERMANENT
        )

    def test_case_insensitive_matching(self) -> None:
        assert (
            classify_error(RuntimeError("Service Not Configured"))
            == ErrorCategory.PERMANENT
        )


class TestClassifyRuntimeErrorUnknown:
    """A RuntimeError without a config message is UNKNOWN."""

    def test_generic_runtime_error_is_unknown(self) -> None:
        assert (
            classify_error(RuntimeError("something unexpected"))
            == ErrorCategory.UNKNOWN
        )

    def test_runtime_error_with_empty_message_is_unknown(self) -> None:
        assert classify_error(RuntimeError()) == ErrorCategory.UNKNOWN


class TestClassifyUnknown:
    """Any other exception type is UNKNOWN."""

    def test_key_error_is_unknown(self) -> None:
        assert classify_error(KeyError("missing")) == ErrorCategory.UNKNOWN

    def test_type_error_is_unknown(self) -> None:
        assert classify_error(TypeError("wrong type")) == ErrorCategory.UNKNOWN

    def test_attribute_error_is_unknown(self) -> None:
        assert classify_error(AttributeError("no attr")) == ErrorCategory.UNKNOWN

    def test_value_error_is_unknown(self) -> None:
        assert classify_error(ValueError("bad value")) == ErrorCategory.UNKNOWN

    def test_exception_base_is_unknown(self) -> None:
        assert classify_error(Exception("generic")) == ErrorCategory.UNKNOWN


class TestErrorCategoryEnum:
    """ErrorCategory is a StrEnum with four members."""

    def test_enum_members(self) -> None:
        members = {e.value for e in ErrorCategory}
        assert members == {"TRANSIENT", "SEMANTIC", "PERMANENT", "UNKNOWN"}

    def test_is_str_enum(self) -> None:
        assert ErrorCategory.TRANSIENT == "TRANSIENT"
        assert ErrorCategory.SEMANTIC == "SEMANTIC"
        assert ErrorCategory.PERMANENT == "PERMANENT"
        assert ErrorCategory.UNKNOWN == "UNKNOWN"
