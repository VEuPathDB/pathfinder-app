"""Classifies exceptions raised by AI tools and formats the directive the agent reads."""

from __future__ import annotations

from enum import StrEnum

import httpx
from veupathdb.errors import VEuPathDBError, WDKError

from pathfinder.platform.errors import AppError

_PERMANENT_PHRASES = (
    "not configured",
    "not available",
    "not enabled",
    "service is disabled",
)

# A WDK status at or above this value is transient.
_WDK_SERVER_ERROR_THRESHOLD = 500

# The character limit for one rendered argument value.
_MAX_ARG_VALUE_CHARS = 120

# The character limit for the whole rendered argument string.
_MAX_ARGS_TOTAL_CHARS = 300


class ErrorCategory(StrEnum):
    """The classification of an exception, which decides how the agent recovers."""

    TRANSIENT = "TRANSIENT"
    SEMANTIC = "SEMANTIC"
    PERMANENT = "PERMANENT"
    UNKNOWN = "UNKNOWN"


def _classify_runtime_error(error: RuntimeError) -> ErrorCategory:
    """Classifies a runtime error as permanent or unknown."""
    message = str(error).lower()
    if any(phrase in message for phrase in _PERMANENT_PHRASES):
        return ErrorCategory.PERMANENT
    return ErrorCategory.UNKNOWN


def classify_error(error: Exception) -> ErrorCategory:
    """Classifies an exception. The checks run from the most specific type to the
    least specific one."""
    if isinstance(error, WDKError):
        is_server_error = error.status >= _WDK_SERVER_ERROR_THRESHOLD
        return ErrorCategory.TRANSIENT if is_server_error else ErrorCategory.SEMANTIC

    if isinstance(error, (AppError, VEuPathDBError)):
        return ErrorCategory.SEMANTIC

    if isinstance(error, (httpx.TimeoutException, httpx.ConnectError, OSError)):
        return ErrorCategory.TRANSIENT

    if isinstance(error, RuntimeError):
        return _classify_runtime_error(error)

    return ErrorCategory.UNKNOWN


def _sanitize_args(tool_args: dict[str, object]) -> str:
    """Renders the tool arguments as a compact key and value string. Each value and
    the whole string are truncated to a fixed length."""
    if not tool_args:
        return ""

    parts: list[str] = []
    for key, value in tool_args.items():
        rendered = repr(value)
        if len(rendered) > _MAX_ARG_VALUE_CHARS:
            rendered = rendered[:_MAX_ARG_VALUE_CHARS] + "..."
        parts.append(f"{key}={rendered}")

    joined = ", ".join(parts)
    if len(joined) > _MAX_ARGS_TOTAL_CHARS:
        joined = joined[:_MAX_ARGS_TOTAL_CHARS] + "..."

    return joined


def build_error_directive(
    *,
    error_type: str,
    tool_name: str,
    tool_args: dict[str, object],
    detail: str,
    next_actions: list[str],
    do_not: str,
) -> str:
    """Builds the structured error directive the agent reads. The caller supplies the
    detail, the next actions and the prohibition, so the guidance is specific."""
    args_str = _sanitize_args(tool_args)
    tool_call = f"{tool_name}({args_str})"

    numbered_actions = "\n".join(
        f"  {i + 1}. {action}" for i, action in enumerate(next_actions)
    )

    return (
        f"ERROR: {error_type}\n"
        f"TOOL: {tool_call}\n"
        f"DETAIL: {detail}\n"
        f"NEXT_ACTIONS:\n{numbered_actions}\n"
        f"DO NOT: {do_not}"
    )


def is_error_directive(content: object) -> bool:
    """Reports whether a tool result is a structured error directive. A directive is
    returned rather than raised, so the caller renders the step as failed."""
    return (
        isinstance(content, str)
        and content.startswith("ERROR: ")
        and "\nNEXT_ACTIONS:\n" in content
    )
