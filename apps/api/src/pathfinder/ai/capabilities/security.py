"""Host wiring for the runtime's input screening: one scanner, one refusal."""

from __future__ import annotations

from assistant_core.capabilities.input_screening import (
    ScreeningRejectionError,
    UserInputScanner,
)

from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import ForbiddenError

_scanner = UserInputScanner(model_dir=get_settings().piguard_model_dir)

_REJECTION_TITLE = "Input rejected by security screening"
_REJECTION_DETAIL = "This message was refused by prompt-injection screening. Rewrite it and send it again."


def warm_up_scanner() -> None:
    """Build the scanners the request path calls, so no request pays the load."""
    _scanner.ensure_loaded()


async def scan_user_input(text: str) -> None:
    """Screen one user message, or refuse the request with a 403."""
    if not get_settings().piguard_enabled:
        return
    try:
        await _scanner.scan_async(text)
    except ScreeningRejectionError as exc:
        raise ForbiddenError(
            title=_REJECTION_TITLE,
            detail=_REJECTION_DETAIL,
        ) from exc


__all__ = ["scan_user_input", "warm_up_scanner"]
