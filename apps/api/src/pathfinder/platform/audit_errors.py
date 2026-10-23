"""The refusals of a gene-model audit that a caller can act on."""

from __future__ import annotations

from pathfinder.platform.errors import AppError, ErrorCode


class AuditNeedsAThreadError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code=ErrorCode.AUDIT_NEEDS_A_THREAD,
            title="An audit starts from a conversation",
            status=409,
            detail=(
                "An audit run belongs to the conversation that starts it, and "
                "this call has no conversation."
            ),
        )
