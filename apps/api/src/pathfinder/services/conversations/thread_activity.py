"""What a thread did between its last answer and the turn now opening.

The durable tasks that finished, and whether the open analysis moved past the
card the thread shows. What moved on the strategy is read from the tree the
thread's spec answers to, not from a snapshot.
"""

from __future__ import annotations

from uuid import UUID

import httpx
from assistant_core.persistence.models import BackgroundTask, ConversationEvent, Message
from assistant_core.platform.logging import get_logger
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.errors import VEuPathDBError

from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.persistence.repositories.conversation_analysis import read_analysis_row
from pathfinder.services.eda.binding import read_analysis

__all__ = [
    "AnalysisDrift",
    "FinishedTask",
    "ThreadActivity",
    "read_thread_activity",
]

logger = get_logger(__name__)

_ANALYSIS_STATE_CHUNK = "data-eda.analysis-state"
_FINISHED_TASK_STATUSES = ("complete", "failed")


class FinishedTask(BaseModel):
    """One durable task that reported after the thread's last answer."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    failed: bool = False


class AnalysisDrift(BaseModel):
    """The open analysis changed after the card the thread shows.

    A change through the tools and a change made on the site read the same.
    """

    model_config = ConfigDict(frozen=True)

    dataset_id: str


class ThreadActivity(BaseModel):
    """The reads a turn briefing is composed from."""

    model_config = ConfigDict(frozen=True)

    finished_tasks: list[FinishedTask] = Field(default_factory=list)
    analysis: AnalysisDrift | None = None


class _ShownAnalysis(BaseModel):
    """The analysis the newest card names; the defaults are a thread with none."""

    model_config = ConfigDict(extra="ignore", alias_generator=to_camel)

    analysis_id: str | None = None
    revision: int = 0
    modification_time: str | None = None

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
    """Read the tasks and the analysis drift this thread has to catch up on."""
    return ThreadActivity(
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
    """Whether the bound analysis moved past the card the thread shows."""
    bound = await read_analysis_row(session, conversation_id=conversation_id)
    if bound is None:
        return None
    shown = await _shown_analysis(session, conversation_id)
    if not await _moved_past(bound, shown):
        return None
    return AnalysisDrift(dataset_id=bound.dataset_id)


async def _moved_past(bound: ConversationAnalysisView, shown: _ShownAnalysis) -> bool:
    """A card of another document, a mutation it has not shown, or a new stamp.

    The document is read only when the binding alone cannot tell.
    """
    if shown.analysis_id not in (None, bound.analysis_id):
        return True
    if bound.revision > shown.revision:
        return True
    if shown.modification_time is None:
        return False
    stamped = await _modification_time(bound)
    return stamped is not None and stamped != shown.modification_time


async def _modification_time(bound: ConversationAnalysisView) -> str | None:
    """The stamp the service holds on the document, or None when it cannot answer."""
    try:
        document = await read_analysis(bound.site_id, analysis_id=bound.analysis_id)
    except (VEuPathDBError, httpx.HTTPError) as exc:
        logger.warning(
            "the open analysis could not be read for the turn briefing",
            analysis_id=bound.analysis_id,
            error=str(exc),
        )
        return None
    return document.modification_time or None


async def _shown_analysis(
    session: AsyncSession, conversation_id: UUID
) -> _ShownAnalysis:
    """The analysis the newest state card on the thread carries."""
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
        return _ShownAnalysis()
    return _AnalysisStateChunk.model_validate(chunk).data
