"""Reading requests, replies and the verification verdict out of the chunk log.

The chunk log is the durable record of what the user saw, so it is what an
extract is made of. Every text that leaves here is redacted first.
"""

from __future__ import annotations

from collections.abc import Sequence

from assistant_core.conversation.ui_message_reducer import USER_MESSAGE_CHUNK_TYPE
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, ConfigDict, Field

from pathfinder.evals.extract import ExtractedTurn, ExtractedVerification
from pathfinder.evals.redaction import redact_text

TEXT_DELTA = "text-delta"
LEDGER_UPDATE = "data-ledger-update"


class ChunkPart(CamelModel):
    model_config = ConfigDict(extra="ignore")

    type: str = ""
    text: str = ""


class ChunkMessage(CamelModel):
    model_config = ConfigDict(extra="ignore")

    id: str = ""
    role: str = ""
    parts: list[ChunkPart] = Field(default_factory=list)

    def text(self) -> str:
        return "".join(part.text for part in self.parts if part.type == "text")


class DigestView(CamelModel):
    model_config = ConfigDict(extra="ignore")

    success: bool
    reason: str = ""
    key_findings: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    pending_checks: list[str] = Field(default_factory=list)


class VerificationView(CamelModel):
    model_config = ConfigDict(extra="ignore")

    digest: DigestView | None = None


class LedgerData(CamelModel):
    model_config = ConfigDict(extra="ignore")

    verification: VerificationView | None = None


class ConversationChunk(CamelModel):
    """One logged chunk, read for the three things an extract needs."""

    model_config = ConfigDict(extra="ignore")

    type: str = ""
    delta: str = ""
    message: ChunkMessage | None = None
    data: LedgerData | None = None


class LoggedChunk(BaseModel):
    """One ``conversation_events`` row, as extraction reads it."""

    model_config = ConfigDict(frozen=True, from_attributes=True, extra="ignore")

    chunk: ConversationChunk


def read_turns(rows: Sequence[LoggedChunk]) -> list[ExtractedTurn]:
    """The exchanges in the log, in order, redacted.

    A user message opens a turn; the text deltas that follow are its reply.
    One id names one message, so a repeated envelope keeps the first.
    """
    requests: list[str] = []
    replies: list[list[str]] = []
    seen: set[str] = set()
    for row in rows:
        chunk = row.chunk
        if chunk.type == USER_MESSAGE_CHUNK_TYPE and chunk.message is not None:
            message = chunk.message
            if message.role != "user" or message.id in seen:
                continue
            if message.id:
                seen.add(message.id)
            requests.append(redact_text(message.text()))
            replies.append([])
        elif chunk.type == TEXT_DELTA and chunk.delta and replies:
            replies[-1].append(chunk.delta)
    return [
        ExtractedTurn(request=request, reply=redact_text("".join(reply)))
        for request, reply in zip(requests, replies, strict=True)
    ]


def read_verification(rows: Sequence[LoggedChunk]) -> ExtractedVerification | None:
    """The last verification verdict in the log, redacted, or None."""
    latest: DigestView | None = None
    for row in rows:
        chunk = row.chunk
        if chunk.type != LEDGER_UPDATE or chunk.data is None:
            continue
        verification = chunk.data.verification
        if verification is not None and verification.digest is not None:
            latest = verification.digest
    if latest is None:
        return None
    return ExtractedVerification(
        success=latest.success,
        reason=redact_text(latest.reason),
        key_findings=[redact_text(line) for line in latest.key_findings],
        caveats=[redact_text(line) for line in latest.caveats],
        pending_checks=latest.pending_checks,
    )


__all__ = ["LoggedChunk", "read_turns", "read_verification"]
