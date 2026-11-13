from __future__ import annotations

from strategist.platform.errors import AppError, ErrorCode


class ForkRefusedError(AppError):
    """A branch point the new thread cannot be given."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            code=ErrorCode.FORK_REFUSED,
            title="Cannot branch this chat",
            status=409,
            detail=reason,
        )


class RevertRefusedError(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            code=ErrorCode.REVERT_REFUSED,
            title="Cannot undo to this message",
            status=409,
            detail=reason,
        )


class EditRefusedError(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            code=ErrorCode.EDIT_REFUSED,
            title="Cannot edit this strategy now",
            status=409,
            detail=reason,
        )


class ThreadBusyError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code=ErrorCode.SESSION_CONFLICT,
            title="This chat is busy",
            status=409,
            detail=(
                "This chat is changing right now. Send the message again in a moment."
            ),
        )
