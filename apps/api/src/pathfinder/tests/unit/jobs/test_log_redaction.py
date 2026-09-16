"""Procrastinate INFO-logs job call_string including all kwargs - without
this filter the VEuPathDB cookie would land on stdout on every job start."""

from __future__ import annotations

import logging

import pytest

from pathfinder.jobs.logging_filters import (
    REDACTION_MARKER,
    RedactSensitiveKwargsFilter,
)

_TOKEN = "secret-cookie-value-12345"


def _emit(
    caplog: pytest.LogCaptureFixture,
    logger_name: str,
    message: str,
) -> logging.LogRecord:
    caplog.clear()
    logger = logging.getLogger(logger_name)
    handler = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]
    logger.addFilter(RedactSensitiveKwargsFilter())
    try:
        with caplog.at_level(logging.INFO, logger=logger_name):
            logger.info(message)
    finally:
        for h in handler:
            logger.removeHandler(h)
    (record,) = caplog.records
    return record


class TestRedactSensitiveKwargsFilter:
    def test_redacts_single_quoted_token_value(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        record = _emit(
            caplog,
            "procrastinate.worker",
            f"Starting job chat_turn:run[1](veupathdb_auth_token='{_TOKEN}')",
        )
        msg = record.getMessage()
        assert _TOKEN not in msg
        assert REDACTION_MARKER in msg
        assert "veupathdb_auth_token=" in msg

    def test_redacts_double_quoted_token_value(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        record = _emit(
            caplog,
            "procrastinate.worker",
            f'Starting job durable:x[1](veupathdb_auth_token="{_TOKEN}")',
        )
        assert _TOKEN not in record.getMessage()
        assert REDACTION_MARKER in record.getMessage()

    def test_passes_through_unrelated_messages(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        record = _emit(
            caplog,
            "procrastinate.worker",
            "Worker loop iteration complete",
        )
        assert record.getMessage() == "Worker loop iteration complete"

    def test_redacts_nested_in_longer_call_string(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        record = _emit(
            caplog,
            "procrastinate.worker",
            (
                f"Starting job chat_turn:run[42]("
                f"payload={{'body': {{...}}, 'user_id': 'abc', "
                f"'turn_id': 'xyz', 'veupathdb_auth_token': '{_TOKEN}'}})"
            ),
        )
        assert _TOKEN not in record.getMessage()

    def test_redacts_multiple_occurrences(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        record = _emit(
            caplog,
            "procrastinate.worker",
            (f"veupathdb_auth_token='{_TOKEN}' veupathdb_auth_token='{_TOKEN}'"),
        )
        msg = record.getMessage()
        assert _TOKEN not in msg
        assert msg.count(REDACTION_MARKER) == 2
