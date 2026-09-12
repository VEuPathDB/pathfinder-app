"""Extraction: finished investigations of consenting users become candidates.

Nothing here writes the corpus. A candidate lands in the staging queue with its
text already redacted, and a human decides whether it becomes a case.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from assistant_core.persistence.models import Conversation, ConversationEvent
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, ValidationError
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy import StrategyAst

from pathfinder.evals.extract import (
    EvalExtract,
    ExtractedStrategy,
)
from pathfinder.evals.redaction import RedactionFailedError
from pathfinder.evals.scoring import structure_signature
from pathfinder.persistence.models import (
    ConversationStrategy,
    ConversationStrategyView,
    EvalStagedCase,
    User,
)
from pathfinder.persistence.repositories.conversation_strategy import strategy_view_of
from pathfinder.persistence.repositories.eval_staging import EvalStagingRepository
from pathfinder.services.eval_data.chunk_reader import (
    LoggedChunk,
    read_turns,
    read_verification,
)

logger = get_logger(__name__)

type SessionFactory = Callable[[], AsyncSession]

DEFAULT_BATCH = 50


class ExtractionReport(CamelModel):
    """What one extraction pass did."""

    model_config = ConfigDict(frozen=True)

    considered: int = 0
    staged: int = 0
    skipped: int = 0


class Candidate(CamelModel):
    """One conversation extraction is about to read."""

    model_config = ConfigDict(frozen=True)

    conversation_id: UUID
    user_id: UUID
    site_id: str
    assistant_id: str
    strategy: ConversationStrategyView


def _candidate_query(
    limit: int,
) -> Select[tuple[UUID, UUID, str, str, ConversationStrategy | None]]:
    # The outer join makes the strategy row nullable, which the select type of
    # the columns does not express.
    selected: Select[tuple[UUID, UUID, str, str, ConversationStrategy | None]] = select(
        Conversation.id,
        Conversation.user_id,
        Conversation.site_id,
        Conversation.assistant_id,
        ConversationStrategy,
    )
    # A thread already in the queue is out of the batch, so a full queue
    # cannot starve the threads behind it.
    already_staged = (
        select(EvalStagedCase.id)
        .where(EvalStagedCase.source_conversation_id == Conversation.id)
        .exists()
    )
    return (
        selected.join(User, User.id == Conversation.user_id)
        .outerjoin(
            ConversationStrategy,
            ConversationStrategy.conversation_id == Conversation.id,
        )
        .where(
            User.eval_data_consent.is_(True),
            Conversation.dismissed_at.is_(None),
            ~already_staged,
        )
        # Newest first: a thread's timestamp moves when it is written to, so a
        # thread that just finished is in the batch and a thread that never
        # finishes cannot crowd it out.
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )


async def find_candidates(session: AsyncSession, *, limit: int) -> list[Candidate]:
    """The conversations a pass will read: consenting users, live threads."""
    rows = (await session.execute(_candidate_query(limit))).all()
    return [
        Candidate(
            conversation_id=row[0],
            user_id=row[1],
            site_id=row[2],
            assistant_id=row[3],
            strategy=strategy_view_of(row[4]),
        )
        for row in rows
    ]


def _extracted_strategy(strategy: ConversationStrategyView) -> ExtractedStrategy | None:
    """The strategy the thread ended with, or None when it built nothing."""
    if not strategy.strategy_ast:
        return None
    try:
        ast = StrategyAst.model_validate(strategy.strategy_ast)
    except ValidationError:
        signature = ""
    else:
        signature = structure_signature(ast)
    return ExtractedStrategy(
        record_type=strategy.record_type,
        step_count=strategy.step_count,
        structure=signature,
        strategy_ast=strategy.strategy_ast,
    )


async def _chunks(session: AsyncSession, conversation_id: UUID) -> list[LoggedChunk]:
    rows = await session.scalars(
        select(ConversationEvent)
        .where(ConversationEvent.conversation_id == conversation_id)
        .order_by(ConversationEvent.id),
    )
    return [LoggedChunk.model_validate(row) for row in rows]


async def build_extract(
    session: AsyncSession,
    candidate: Candidate,
) -> EvalExtract | None:
    """The candidate as an extract, or None when the thread did not finish.

    A thread with no verification verdict is not a finished investigation, so
    it is not a case.
    """
    rows = await _chunks(session, candidate.conversation_id)
    verification = read_verification(rows)
    if verification is None:
        return None
    turns = read_turns(rows)
    if not turns:
        return None
    return EvalExtract(
        site_id=candidate.site_id,
        assistant_id=candidate.assistant_id,
        turns=turns,
        strategy=_extracted_strategy(candidate.strategy),
        verification=verification,
    )


async def extract_eval_candidates(
    *,
    session_factory: SessionFactory = async_session_factory,
    limit: int = DEFAULT_BATCH,
) -> ExtractionReport:
    """One extraction pass. Idempotent: a thread already known stages nothing."""
    staging = EvalStagingRepository(session_factory=session_factory)
    considered = 0
    staged = 0
    async with session_factory() as session:
        candidates = await find_candidates(session, limit=limit)
        extracts: list[tuple[Candidate, EvalExtract]] = []
        for candidate in candidates:
            considered += 1
            try:
                extract = await build_extract(session, candidate)
            except RedactionFailedError:
                logger.warning(
                    "eval extraction refused a candidate that failed redaction",
                    site_id=candidate.site_id,
                )
                continue
            if extract is not None:
                extracts.append((candidate, extract))

    for candidate, extract in extracts:
        written = await staging.stage(
            user_id=candidate.user_id,
            conversation_id=candidate.conversation_id,
            extract=extract,
        )
        if written is not None:
            staged += 1

    report = ExtractionReport(
        considered=considered,
        staged=staged,
        skipped=considered - staged,
    )
    logger.info(
        "eval extraction pass",
        considered=report.considered,
        staged=report.staged,
    )
    return report


__all__ = [
    "Candidate",
    "ExtractionReport",
    "build_extract",
    "extract_eval_candidates",
    "find_candidates",
]
