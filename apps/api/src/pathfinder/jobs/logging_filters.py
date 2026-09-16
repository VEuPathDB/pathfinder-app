"""Stdlib logging filters for the procrastinate worker.

Procrastinate INFO-logs ``Starting job <name>[<id>](<kwargs-repr>)`` for every
job start (``procrastinate/worker.py``). Because our ``chat_turn:run`` and
``durable:*`` payloads now carry the user's VEuPathDB auth cookie, that raw
value would otherwise land on stdout. This filter scrubs the value of any
key in ``_SENSITIVE_KEYS`` from both single- and double-quoted forms before
the handler emits the record.
"""

from __future__ import annotations

import logging
import re

REDACTION_MARKER = "***REDACTED***"

_SENSITIVE_KEYS: tuple[str, ...] = ("veupathdb_auth_token",)


def _build_patterns() -> list[tuple[re.Pattern[str], str]]:
    """Build (pattern, replacement) pairs that match a sensitive key bound
    to a quoted value in three common forms:

    - ``key='value'`` / ``key="value"`` (kwarg / attribute repr)
    - ``'key': 'value'`` / ``"key": "value"`` (dict repr with str keys)
    - ``key: 'value'`` / ``key: "value"`` (bare-colon variant)
    """
    patterns: list[tuple[re.Pattern[str], str]] = []
    for key in _SENSITIVE_KEYS:
        escaped = re.escape(key)
        # Left-hand side accepts bare key or quoted key, followed by = or : with
        # optional whitespace. Right-hand side is a single- or double-quoted
        # string. Group 1 captures the LHS so replacement preserves the caller's
        # punctuation (dict colon vs kwarg equals).
        patterns.append(
            (
                re.compile(
                    rf"""(?P<lhs>(?:'{escaped}'|"{escaped}"|{escaped})\s*[:=]\s*)"""
                    r"""(?:'[^']*'|"[^"]*")""",
                ),
                rf"\g<lhs>'{REDACTION_MARKER}'",
            ),
        )
    return patterns


_PATTERNS: list[tuple[re.Pattern[str], str]] = _build_patterns()


class RedactSensitiveKwargsFilter(logging.Filter):
    """Scrub sensitive kwargs from emitted log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for pattern, replacement in _PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def install_procrastinate_redaction() -> None:
    """Attach ``RedactSensitiveKwargsFilter`` to every procrastinate logger.

    ``logging.Filter`` does **not** propagate from parent to child loggers -
    only handlers do. Procrastinate uses at least three logger names
    (``procrastinate``, ``procrastinate.worker``, ``procrastinate.worker.worker``);
    miss any and a secret leaks through. We attach the filter to every
    logger whose name starts with ``procrastinate`` that's been created so
    far, and register a root-level handler-side filter for any that come
    online later.

    Idempotent - re-invocation does not add duplicate filters.
    """
    filt = RedactSensitiveKwargsFilter()
    manager = logging.Logger.manager
    candidate_names = {"procrastinate"}
    for logger_name in manager.loggerDict:
        if logger_name == "procrastinate" or logger_name.startswith(
            "procrastinate.",
        ):
            candidate_names.add(logger_name)
    for logger_name in candidate_names:
        logger = logging.getLogger(logger_name)
        if not any(isinstance(f, RedactSensitiveKwargsFilter) for f in logger.filters):
            logger.addFilter(filt)
    # Root-handler fallback: catches any procrastinate sub-logger created
    # after this call returns, since child records propagate up to root
    # handlers (but not parent filters).
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, RedactSensitiveKwargsFilter) for f in handler.filters):
            handler.addFilter(filt)


__all__ = [
    "REDACTION_MARKER",
    "RedactSensitiveKwargsFilter",
    "install_procrastinate_redaction",
]
