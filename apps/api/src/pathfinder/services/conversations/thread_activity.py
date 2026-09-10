"""What a thread did between its last answer and the turn now opening.

The strategy the two newest snapshots hold, the durable tasks that finished,
and how far the open analysis has moved past the card the thread shows.
"""

from __future__ import annotations

from uuid import UUID

from assistant_core.persistence.models import BackgroundTask, ConversationEvent, Message
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy.strategy_ast import StrategyAst

from pathfinder.domain.strategy.revision import parse_strategy_ast
from pathfinder.persistence.repositories.conversation_analysis import read_analysis_row
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)

__all__ = [
    "AnalysisDrift",
    "FinishedTask",
    "ThreadActivity",
    "read_thread_activity",
]

_ANALYSIS_STATE_CHUNK = "data-eda.analysis-state"
_FINISHED_TASK_STATUSES = ("complete", "failed")


class FinishedTask(BaseModel):
    """One durable task that reported after the thread's last answer."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    failed: bool = False


class AnalysisDrift(BaseModel):
    """How many mutations the open analysis has taken past the shown card."""

    model_config = ConfigDict(frozen=True)

    dataset_id: str
    revisions_ahead: int


class ThreadActivity(BaseModel):
    """The reads a turn briefing is composed from."""

    model_config = ConfigDict(frozen=True)

    strategy_before: StrategyAst | None = None
    strategy_after: StrategyAst | None = None
    finished_tasks: list[FinishedTask] = Field(default_factory=list)
    analysis: AnalysisDrift | None = None


class _ShownAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    revision: int = 0

    @field_validator("revision", mode="before")
    @classmethod
    def _unknown_revision_is_zero(cls, value: object) -> object:
        return 0 if value is None else value


class _AnalysisStateChunk(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: _ShownAnalysis = Field(default_factory=_ShownAnalysis)


async def read_thread_activity(
    session: AsyncSession,
    *,
    conversation_id: UUID,
) -> ThreadActivity:
    """Read what moved on this thread since it last answered."""
    snapshots = await StrategyRevisionRepository(session).newest(
        conversation_id,
        limit=2,
    )
    asts = [parse_strategy_ast(snapshot.strategy_ast) for snapshot in snapshots]
    return ThreadActivity(
        strategy_after=asts[0] if asts else None,
        strategy_before=asts[1] if len(asts) > 1 else None,
        finished_tasks=await _finished_tasks(session, conversation_id),
        analysis=await _analysis_drift(session, conversation_id),
    )


async def _finished_tasks(
    session: AsyncSession,
    conversation_id: UUID,
) -> list[FinishedTask]:
    """The tasks that reported after the newest assistant message.

    A thread that has not answered yet has nothing to catch up on.
    """
    last_answer = await session.scalar(
        select(func.max(Message.created_at)).where(
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
        ),
    )
    if last_answer is None:
        return []
    rows = await session.execute(
        select(BackgroundTask.tool_name, BackgroundTask.status)
        .where(
            BackgroundTask.conversation_id == conversation_id,
            BackgroundTask.status.in_(_FINISHED_TASK_STATUSES),
            BackgroundTask.completed_at > last_answer,
        )
        .order_by(BackgroundTask.completed_at),
    )
    return [
        FinishedTask(tool_name=tool_name, failed=status == "failed")
        for tool_name, status in rows.all()
    ]


async def _analysis_drift(
    session: AsyncSession,
    conversation_id: UUID,
) -> AnalysisDrift | None:
    """How far the bound analysis has moved past the card the thread shows."""
    bound = await read_analysis_row(session, conversation_id=conversation_id)
    if bound is None:
        return None
    ahead = bound.revision - await _shown_revision(session, conversation_id)
    if ahead <= 0:
        return None
    return AnalysisDrift(dataset_id=bound.dataset_id, revisions_ahead=ahead)


async def _shown_revision(session: AsyncSession, conversation_id: UUID) -> int:
    """The analysis revision the newest state card on the thread carries."""
    chunk = await session.scalar(
        select(ConversationEvent.chunk)
        .where(
            ConversationEvent.conversation_id == conversation_id,
            ConversationEvent.chunk["type"].as_string() == _ANALYSIS_STATE_CHUNK,
        )
        .order_by(desc(ConversationEvent.id))
        .limit(1),
    )
    if chunk is None:
        return 0
    return _AnalysisStateChunk.model_validate(chunk).data.revision
