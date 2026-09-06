"""What a branch and a revert do to the thread's EDA binding.

The thread's own log records every binding state it showed, so neither
operation needs a history of its own: the newest ``data-eda.analysis-state``
part that survives the cut names the analysis, the dataset and the filters the
transcript still describes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from assistant_core.persistence.models import ConversationEvent
from assistant_core.platform.logging import get_logger
from pydantic import BaseModel, ConfigDict, TypeAdapter
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.eda.errors import EdaNotFoundError
from veupathdb.eda.models import EdaFilter
from veupathdb.errors import VEuPathDBError

from pathfinder.domain.eda_parts import EdaAnalysisState
from pathfinder.persistence.models import ConversationAnalysisView
from pathfinder.persistence.repositories.conversation_analysis import (
    bind_analysis_row,
    bump_analysis_row,
    read_analysis_row,
    unbind_analysis_row,
)
from pathfinder.platform.errors import AppError
from pathfinder.services.eda.authoring import open_analysis, patch_subset
from pathfinder.services.eda.binding import read_analysis

logger = get_logger(__name__)

_ANALYSIS_STATE = "data-eda.analysis-state"
_FILTERS: TypeAdapter[list[EdaFilter]] = TypeAdapter(list[EdaFilter])

__all__ = [
    "AdoptBinding",
    "DropBinding",
    "KeepBinding",
    "binding_plan",
    "branch_thread_binding",
    "logs_a_binding",
    "newest_analysis_state",
    "restore_thread_binding",
]


class _AnalysisStateChunk(BaseModel):
    """The analysis-state part as the log stores it."""

    model_config = ConfigDict(extra="ignore")

    data: EdaAnalysisState


@dataclass(frozen=True, slots=True)
class KeepBinding:
    """The row on disk already agrees with the log."""


@dataclass(frozen=True, slots=True)
class DropBinding:
    """The log records no analysis, so the thread has none open."""


@dataclass(frozen=True, slots=True)
class AdoptBinding:
    """The thread takes the recorded state. ``rebind`` names a new document."""

    recorded: EdaAnalysisState
    rebind: bool


type BindingPlan = KeepBinding | DropBinding | AdoptBinding


def binding_plan(
    *,
    recorded: EdaAnalysisState | None,
    bound: ConversationAnalysisView | None,
    logged: bool,
) -> BindingPlan:
    """The binding the surviving log describes, against the row on disk.

    ``logged`` is whether the thread's log recorded any binding state at all
    before the cut. A thread that recorded none has a binding the log never
    saw, so the log cannot say the study was opened by a deleted turn.
    """
    if recorded is None:
        return DropBinding() if bound is not None and logged else KeepBinding()
    return AdoptBinding(
        recorded=recorded,
        rebind=bound is None or bound.analysis_id != recorded.analysis_id,
    )


async def newest_analysis_state(
    session: AsyncSession,
    *,
    conversation_id: UUID,
) -> EdaAnalysisState | None:
    """The last analysis-state part this thread's log still holds."""
    chunk = await session.scalar(
        select(ConversationEvent.chunk)
        .where(
            ConversationEvent.conversation_id == conversation_id,
            ConversationEvent.chunk["type"].astext == _ANALYSIS_STATE,
        )
        .order_by(ConversationEvent.id.desc())
        .limit(1),
    )
    if chunk is None:
        return None
    return _AnalysisStateChunk.model_validate(chunk).data


async def logs_a_binding(
    session: AsyncSession,
    *,
    conversation_id: UUID,
) -> bool:
    """Whether this thread's log records any binding state at all.

    A revert reads this before the cut, because a thread that recorded none
    holds a binding the log never described.
    """
    return bool(
        await session.scalar(
            select(
                exists().where(
                    ConversationEvent.conversation_id == conversation_id,
                    ConversationEvent.chunk["type"].astext == _ANALYSIS_STATE,
                ),
            ),
        )
    )


async def _fresh_document(
    recorded: EdaAnalysisState,
    filters: Sequence[EdaFilter],
) -> str:
    """Create a document of this thread's own for the recorded descriptor."""
    analysis_id = await open_analysis(
        recorded.site_id,
        dataset_id=recorded.dataset_id,
        display_name=recorded.display_name,
    )
    if filters:
        await patch_subset(
            recorded.site_id,
            analysis_id=analysis_id,
            dataset_id=recorded.dataset_id,
            filters=filters,
        )
    return analysis_id


async def _recorded_or_fresh_document(
    recorded: EdaAnalysisState,
    filters: Sequence[EdaFilter],
) -> str:
    """The recorded document with its recorded subset, or a new one when it is gone.

    Replacing a binding leaves the document it replaced on the service, so the
    recorded id normally still resolves.
    """
    recorded_id: str = recorded.analysis_id
    try:
        await patch_subset(
            recorded.site_id,
            analysis_id=recorded_id,
            dataset_id=recorded.dataset_id,
            filters=filters,
        )
    except EdaNotFoundError:
        return await _fresh_document(recorded, filters)
    return recorded_id


async def _bind_and_count(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    recorded: EdaAnalysisState,
    analysis_id: str,
) -> None:
    await bind_analysis_row(
        session,
        conversation_id=conversation_id,
        site_id=recorded.site_id,
        dataset_id=recorded.dataset_id,
        analysis_id=analysis_id,
    )
    await bump_analysis_row(session, conversation_id=conversation_id)


async def _adopt(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    plan: AdoptBinding,
) -> None:
    recorded = plan.recorded
    filters = _FILTERS.validate_python(recorded.filters)
    if plan.rebind:
        await _bind_and_count(
            session,
            conversation_id=conversation_id,
            recorded=recorded,
            analysis_id=await _recorded_or_fresh_document(recorded, filters),
        )
        return
    live = await read_analysis(recorded.site_id, analysis_id=recorded.analysis_id)
    if list(live.descriptor.subset.descriptor) == filters:
        return
    await patch_subset(
        recorded.site_id,
        analysis_id=recorded.analysis_id,
        dataset_id=recorded.dataset_id,
        filters=filters,
    )
    await bump_analysis_row(session, conversation_id=conversation_id)


async def restore_thread_binding(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    logged: bool,
) -> None:
    """Put the binding back where the surviving log leaves it.

    ``logged`` comes from :func:`logs_a_binding`, read before the cut. A
    refusal from the study service leaves the binding as it was: the revert
    itself must not fail over a document nobody can reach.
    """
    plan = binding_plan(
        recorded=await newest_analysis_state(session, conversation_id=conversation_id),
        bound=await read_analysis_row(session, conversation_id=conversation_id),
        logged=logged,
    )
    match plan:
        case KeepBinding():
            return
        case DropBinding():
            await unbind_analysis_row(session, conversation_id=conversation_id)
        case AdoptBinding():
            try:
                await _adopt(session, conversation_id=conversation_id, plan=plan)
            except (AppError, VEuPathDBError) as exc:
                logger.warning(
                    "revert kept the EDA binding: the study service refused",
                    conversation_id=str(conversation_id),
                    analysis_id=plan.recorded.analysis_id,
                    error=str(exc),
                )


async def branch_thread_binding(
    session: AsyncSession,
    *,
    conversation_id: UUID,
) -> None:
    """Open a document of the branch's own for the state its copied log records.

    A branch never authors its source's analysis, so the descriptor is copied
    and the document is not. A refusal leaves the branch with no study open.
    """
    recorded = await newest_analysis_state(session, conversation_id=conversation_id)
    if recorded is None:
        return
    filters = _FILTERS.validate_python(recorded.filters)
    try:
        analysis_id = await _fresh_document(recorded, filters)
    except (AppError, VEuPathDBError) as exc:
        logger.warning(
            "branch opened with no study: the study service refused a document",
            conversation_id=str(conversation_id),
            source_analysis_id=recorded.analysis_id,
            error=str(exc),
        )
        return
    await _bind_and_count(
        session,
        conversation_id=conversation_id,
        recorded=recorded,
        analysis_id=analysis_id,
    )
