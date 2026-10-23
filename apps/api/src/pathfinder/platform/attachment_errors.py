"""The refusals of a file a user attaches to a message."""

from __future__ import annotations

from pathfinder.platform.errors import AppError, ErrorCode


class AttachmentTooLargeError(AppError):
    """A message carries more attachment bytes, or more attachments, than a turn takes."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            code=ErrorCode.ATTACHMENT_TOO_LARGE,
            title="Attachment too large",
            status=413,
            detail=detail,
        )


class AttachmentNotReadableError(AppError):
    """An attachment of a kind the model that reads the message cannot read."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            code=ErrorCode.ATTACHMENT_NOT_READABLE,
            title="Attachment not readable",
            status=422,
            detail=detail,
        )
