"""``install_procrastinate_redaction`` must cover every procrastinate logger
- filters do NOT propagate from parent to child, so attaching only to
``procrastinate`` leaves ``procrastinate.worker.worker`` unredacted."""

from __future__ import annotations

import logging

import pytest

from pathfinder.jobs.logging_filters import (
    REDACTION_MARKER,
    RedactSensitiveKwargsFilter,
    install_procrastinate_redaction,
)


@pytest.fixture(autouse=True)
def _cleanup() -> None:
    for name in (
        "procrastinate",
        "procrastinate.worker",
        "procrastinate.worker.worker",
        "procrastinate.periodic",
    ):
        logger = logging.getLogger(name)
        logger.filters = [
            f for f in logger.filters if not isinstance(f, RedactSensitiveKwargsFilter)
        ]


def _grand_child_logger() -> logging.Logger:
    """The name procrastinate itself actually uses for start/end messages."""
    return logging.getLogger("procrastinate.worker.worker")


def test_install_redacts_grand_child_logger(
    caplog: pytest.LogCaptureFixture,
) -> None:
    install_procrastinate_redaction()
    logger = _grand_child_logger()
    token = "token-should-not-leak"
    with caplog.at_level(logging.INFO, logger=logger.name):
        logger.info(f"Starting job echo[1](veupathdb_auth_token='{token}')")
    (record,) = caplog.records
    msg = record.getMessage()
    assert token not in msg
    assert REDACTION_MARKER in msg


def test_install_is_idempotent(caplog: pytest.LogCaptureFixture) -> None:
    install_procrastinate_redaction()
    install_procrastinate_redaction()
    logger = _grand_child_logger()
    filters_of_type = [
        f for f in logger.filters if isinstance(f, RedactSensitiveKwargsFilter)
    ]
    assert len(filters_of_type) == 1


def test_install_covers_loggers_created_after_install() -> None:
    """Root-handler fallback catches procrastinate children that are only
    instantiated by the library's own code later."""
    install_procrastinate_redaction()
    late_logger = logging.getLogger("procrastinate.latecomer")
    # Even if the direct logger has no filter, records propagate to root
    # and root handlers should redact. Verify a RedactSensitiveKwargsFilter
    # is attached to at least one root handler.
    root_handlers_with_filter = [
        h
        for h in logging.getLogger().handlers
        if any(isinstance(f, RedactSensitiveKwargsFilter) for f in h.filters)
    ]
    assert root_handlers_with_filter, (
        "Root handler must carry the redaction filter so late-created "
        "procrastinate sub-loggers still have their records scrubbed."
    )
    del late_logger  # silence linter
