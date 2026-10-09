"""Reading requests, the facts each turn showed, replies, the verification
verdict and its evidence card out of the chunk log.

The chunk log is the durable record of what the user saw, so it is what an
extract is made of. Every text that leaves here is redacted first.
"""

from __future__ import annotations

from collections.abc import Sequence

from assistant_core.conversation.ui_message_reducer import USER_MESSAGE_CHUNK_TYPE
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from pathfinder.domain.caveats import Caveat, Gap
from pathfinder.domain.citations import (
    Citation,
)
from pathfinder.domain.evidence import (
    ColumnFit,
    EvidenceCard,
    RequirementCheck,
    SampledGene,
    VerificationReview,
)
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.evals.extract import ExtractedTurn, ExtractedVerification
from pathfinder.evals.redaction import redact_text

TEXT_DELTA = "text-delta"
FACTS = "data-facts"
LEDGER_UPDATE = "data-ledger-update"
EVIDENCE_CARD = "data-evidence-card"
TURN_WITHDRAWN = "data-turn-withdrawn"


class WithdrawnPrompt(CamelModel):
    model_config = ConfigDict(extra="ignore")

    message_id: str


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
    caveats: list[Caveat] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    pending_checks: list[str] = Field(default_factory=list)
    review: VerificationReview = Field(default_factory=VerificationReview)


class VerificationView(CamelModel):
    model_config = ConfigDict(extra="ignore")

    digest: DigestView | None = None


class LedgerData(CamelModel):
    model_config = ConfigDict(extra="ignore")

    verification: VerificationView | None = None


class ConversationChunk(CamelModel):
    """One logged chunk, read for the four things an extract needs."""

    model_config = ConfigDict(extra="ignore")

    type: str = ""
    delta: str = ""
    message: ChunkMessage | None = None
    data: dict[str, JsonValue] | None = None


class LoggedChunk(BaseModel):
    """One ``conversation_events`` row, as extraction reads it."""

    model_config = ConfigDict(frozen=True, from_attributes=True, extra="ignore")

    chunk: ConversationChunk


def read_turns(rows: Sequence[LoggedChunk]) -> list[ExtractedTurn]:
    """The exchanges in the log, in order, redacted.

    A user message opens a turn; the text deltas that follow are its reply and
    the last facts part that follows is what it showed beside the reply. One id
    names one message, so a repeated envelope keeps the first. A prompt the
    thread withdrew is no turn.
    """
    ids: list[str] = []
    requests: list[str] = []
    replies: list[list[str]] = []
    shown: list[TurnFacts | None] = []
    withdrawn: set[str] = set()
    for row in rows:
        chunk = row.chunk
        if chunk.type == USER_MESSAGE_CHUNK_TYPE and chunk.message is not None:
            message = chunk.message
            if message.role != "user" or (message.id and message.id in ids):
                continue
            ids.append(message.id)
            requests.append(redact_text(message.text()))
            replies.append([])
            shown.append(None)
        elif chunk.type == TEXT_DELTA and chunk.delta and replies:
            replies[-1].append(chunk.delta)
        elif chunk.type == FACTS and chunk.data is not None and shown:
            shown[-1] = TurnFacts.model_validate(chunk.data).redacted(redact_text)
        elif chunk.type == TURN_WITHDRAWN and chunk.data is not None:
            withdrawn.add(WithdrawnPrompt.model_validate(chunk.data).message_id)
    return [
        ExtractedTurn(request=request, reply=redact_text("".join(reply)), facts=facts)
        for message_id, request, reply, facts in zip(
            ids, requests, replies, shown, strict=True
        )
        if message_id not in withdrawn
    ]


def _redacted_row(row: RequirementCheck) -> RequirementCheck:
    return row.model_copy(
        update={"text": redact_text(row.text), "note": redact_text(row.note)}
    )


def _redacted_fit(fit: ColumnFit) -> ColumnFit:
    return fit.model_copy(
        update={
            "criterion_text": redact_text(fit.criterion_text),
            "display_name": redact_text(fit.display_name),
            "bound_value": redact_text(fit.bound_value),
        }
    )


def _redacted_gene(gene: SampledGene) -> SampledGene:
    return gene.model_copy(
        update={
            "product": redact_text(gene.product),
            "organism": redact_text(gene.organism),
            "why": redact_text(gene.why),
        }
    )


def _redacted_source(cited: Citation) -> Citation:
    return cited.model_copy(
        update={
            "label": redact_text(cited.label),
            "why": redact_text(cited.why),
            "url": None if cited.url is None else redact_text(cited.url),
            "doi": None if cited.doi is None else redact_text(cited.doi),
            "pmid": None if cited.pmid is None else redact_text(cited.pmid),
        }
    )


def _redacted_review(review: VerificationReview) -> VerificationReview:
    """The review with every text on it redacted; gene ids are not identity."""
    return review.model_copy(
        update={
            "requirements": [_redacted_row(row) for row in review.requirements],
            "column_fits": [_redacted_fit(fit) for fit in review.column_fits],
            "sampled_genes": [_redacted_gene(g) for g in review.sampled_genes],
            "sources": [_redacted_source(cited) for cited in review.sources],
        }
    )


def _redacted(card: EvidenceCard) -> EvidenceCard:
    """The card with every text on it redacted; counts and ids are not identity."""
    return card.model_copy(
        update={
            "strategy_url": (
                None if card.strategy_url is None else redact_text(card.strategy_url)
            ),
            "steps": [
                step.model_copy(update={"title": redact_text(step.title)})
                for step in card.steps
            ],
            "controls": [
                test.model_copy(
                    update={
                        "tested_label": redact_text(test.tested_label),
                        "control_set": (
                            None
                            if test.control_set is None
                            else test.control_set.redacted(redact_text)
                        ),
                    }
                )
                for test in card.controls
            ],
            "citations": [
                cited.model_copy(
                    update={
                        "criterion_text": redact_text(cited.criterion_text),
                        "references": [redact_text(r) for r in cited.references],
                    }
                )
                for cited in card.citations
            ],
            "pending_checks": [redact_text(p) for p in card.pending_checks],
            "review": _redacted_review(card.review),
        }
    )


def read_evidence(rows: Sequence[LoggedChunk]) -> EvidenceCard | None:
    """The last evidence card in the log, redacted, or None."""
    latest: EvidenceCard | None = None
    for row in rows:
        chunk = row.chunk
        if chunk.type == EVIDENCE_CARD and chunk.data is not None:
            latest = EvidenceCard.model_validate(chunk.data)
    return None if latest is None else _redacted(latest)


def read_verification(rows: Sequence[LoggedChunk]) -> ExtractedVerification | None:
    """The last verification verdict in the log and its card, redacted, or None."""
    latest: DigestView | None = None
    for row in rows:
        chunk = row.chunk
        if chunk.type != LEDGER_UPDATE or chunk.data is None:
            continue
        verification = LedgerData.model_validate(chunk.data).verification
        if verification is not None and verification.digest is not None:
            latest = verification.digest
    if latest is None:
        return None
    return ExtractedVerification(
        success=latest.success,
        reason=redact_text(latest.reason),
        key_findings=[redact_text(line) for line in latest.key_findings],
        caveats=[caveat.redacted(redact_text) for caveat in latest.caveats],
        gaps=[gap.redacted(redact_text) for gap in latest.gaps],
        pending_checks=[redact_text(step) for step in latest.pending_checks],
        requirements=[_redacted_row(row) for row in latest.review.requirements],
        evidence=read_evidence(rows),
    )


__all__ = ["LoggedChunk", "read_evidence", "read_turns", "read_verification"]
