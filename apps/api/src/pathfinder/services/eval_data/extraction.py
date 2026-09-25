"""Extraction: finished investigations of consenting users become candidates.

Nothing here writes the corpus. A candidate lands in the staging queue with its
text already redacted, and a human decides whether it becomes a case.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from uuid import UUID

from assistant_core.persistence.models import Conversation, ConversationEvent
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy import StrategyAst, walk

from pathfinder.domain.strategy.step_words import StepWords
from pathfinder.evals.extract import (
    EvalExtract,
    ExtractedStrategy,
)
from pathfinder.evals.redaction import RedactionFailedError, redact_text
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
from pathfinder.services.strategies.schemas import step_rationale_of

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


def extracted_strategy(
    *,
    record_type: str | None,
    step_count: int,
    strategy_ast: JSONObject,
) -> ExtractedStrategy | None:
    """The strategy a snapshot holds, its texts redacted, or None when it built
    nothing."""
    if not strategy_ast:
        return None
    try:
        ast = _redacted(StrategyAst.model_validate(strategy_ast))
    except ValidationError:
        return _unparsed_strategy(
            record_type=record_type, step_count=step_count, strategy_ast=strategy_ast
        )
    words = StepWords.of(ast)
    nodes = [node for root in (ast.root, *ast.detached_roots) for node in walk(root)]
    return ExtractedStrategy(
        record_type=record_type,
        step_count=step_count,
        structure=structure_signature(ast),
        strategy_ast=ast.model_dump(by_alias=True, mode="json"),
        rationales={
            node.id: reason
            for node in nodes
            if (reason := step_rationale_of(words, node)) is not None
        },
    )


class _StoredTexts(CamelModel):
    """The texts a stored strategy carries, read without its tree."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    description: str | None = None
    metadata: StepWords | None = None


def _unparsed_strategy(
    *,
    record_type: str | None,
    step_count: int,
    strategy_ast: JSONObject,
) -> ExtractedStrategy | None:
    """A stored strategy whose tree does not parse, its texts redacted.

    None when its texts cannot be read either, since nothing unredacted stages.
    """
    try:
        stored = _StoredTexts.model_validate(strategy_ast)
    except ValidationError:
        return None
    words = _redacted_words(stored.metadata or StepWords())
    texts: JSONObject = {
        "name": None if stored.name is None else redact_text(stored.name),
        "description": (
            None if stored.description is None else redact_text(stored.description)
        ),
        "metadata": None
        if words.empty
        else words.model_dump(by_alias=True, mode="json"),
    }
    return ExtractedStrategy(
        record_type=record_type,
        step_count=step_count,
        strategy_ast=strategy_ast
        | {key: value for key, value in texts.items() if key in strategy_ast},
    )


def _redacted(ast: StrategyAst) -> StrategyAst:
    """The strategy with every text a researcher or a model wrote redacted."""
    redacted = _redacted_words(StepWords.of(ast))
    return ast.model_copy(
        update={
            "name": None if ast.name is None else redact_text(ast.name),
            "description": (
                None if ast.description is None else redact_text(ast.description)
            ),
            "metadata": (
                None
                if redacted.empty
                else redacted.model_dump(by_alias=True, mode="json")
            ),
        }
    )


def _redacted_words(words: StepWords) -> StepWords:
    """The step words with every text a researcher or a model wrote redacted."""
    return words.model_copy(
        update={
            "criterion_texts": {
                step: redact_text(text) for step, text in words.criterion_texts.items()
            },
            "rationales": {
                step: reason.redacted(redact_text)
                for step, reason in words.rationales.items()
            },
        }
    )


class _ErrorContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    error: object = None


class _ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ctx: _ErrorContext | None = None


_ERROR_DETAILS = TypeAdapter(list[_ErrorDetail])


def failed_redaction(exc: ValidationError) -> bool:
    """Whether an extract was refused because a text still carries an identity.

    Pydantic reports the redaction failure its validator raised as the context
    of the validation error.
    """
    return any(
        isinstance(detail.ctx.error, RedactionFailedError)
        for detail in _ERROR_DETAILS.validate_python(exc.errors())
        if detail.ctx is not None
    )


async def logged_chunks(
    session: AsyncSession,
    conversation_id: UUID,
    *,
    through: int | None = None,
) -> list[LoggedChunk]:
    """The thread's log in order, up to and including row ``through``."""
    query = select(ConversationEvent).where(
        ConversationEvent.conversation_id == conversation_id
    )
    if through is not None:
        query = query.where(ConversationEvent.id <= through)
    rows = await session.scalars(query.order_by(ConversationEvent.id))
    return [LoggedChunk.model_validate(row) for row in rows]


def extract_from_rows(
    *,
    site_id: str,
    assistant_id: str,
    rows: Sequence[LoggedChunk],
    strategy: ExtractedStrategy | None,
) -> EvalExtract | None:
    """The logged rows as an extract, or None when they hold no request."""
    turns = read_turns(rows)
    if not turns:
        return None
    return EvalExtract(
        site_id=site_id,
        assistant_id=assistant_id,
        turns=turns,
        strategy=strategy,
        verification=read_verification(rows),
    )


async def build_extract(
    session: AsyncSession,
    candidate: Candidate,
) -> EvalExtract | None:
    """The candidate as an extract, or None when the thread did not finish.

    A thread with no verification verdict is not a finished investigation, so
    it is not a case.
    """
    rows = await logged_chunks(session, candidate.conversation_id)
    if read_verification(rows) is None:
        return None
    return extract_from_rows(
        site_id=candidate.site_id,
        assistant_id=candidate.assistant_id,
        rows=rows,
        strategy=extracted_strategy(
            record_type=candidate.strategy.record_type,
            step_count=candidate.strategy.step_count,
            strategy_ast=candidate.strategy.strategy_ast,
        ),
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
            except ValidationError as exc:
                if not failed_redaction(exc):
                    raise
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
    "extract_from_rows",
    "extracted_strategy",
    "failed_redaction",
    "find_candidates",
    "logged_chunks",
]
