"""One test's structlog configuration may not decide where a later test logs.

The configuration is process-wide, so the suite restores it around every test.
"""

from __future__ import annotations

import sys

import pytest
import structlog

from pathfinder.tests._support.logs import logged_events

_LOGGER = "pathfinder.tests.logger_leak"
_MARKER = "leak marker"


def test_a_test_may_route_the_global_logger_to_stderr() -> None:
    """A test that reconfigures structlog is allowed to."""
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))

    assert structlog.is_configured()


def test_the_next_test_logs_through_the_suites_own_configuration(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The next test gets the suite's own configuration back.

    The suite configures logging the way a served process does, so a record
    reaches stdlib logging and nothing is written to stderr by hand.
    """
    structlog.get_logger(_LOGGER).warning(_MARKER)

    assert logged_events(caplog.records) == [_MARKER]
    assert capsys.readouterr().err == ""
