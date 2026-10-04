"""What an EDA compute body reads of its thread, and the parts it writes to it."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from assistant_core.conversation.event_writer import append_chunk
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.eda import (
    EdaAnalysisDetail,
    EdaFilter,
    EdaPermissionEntry,
    EdaStudyDetail,
)

from pathfinder.ai.tools.standalone.eda_stream_parts import eda_analysis_state_chunk
from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.services.eda.binding import (
    analysis_state,
    bound_conversation_analysis,
    bump_analysis_revision,
    read_analysis,
)
from pathfinder.services.eda.catalog import get_study_detail_for_dataset
from pathfinder.services.eda.description import permission_facts


@dataclass(frozen=True, slots=True)
class BoundStudy:
    """The thread's open analysis, the study it reads and the account's grant."""

    binding: ConversationAnalysisView
    entry: EdaPermissionEntry
    study: EdaStudyDetail
    analysis: EdaAnalysisDetail

    @property
    def filters(self) -> list[EdaFilter]:
        """The subset the analysis holds. A job id hashes it, so a compute runs on it."""
        return list(self.analysis.descriptor.subset.descriptor)


async def bound_study(*, conversation_id: UUID) -> BoundStudy:
    """The open analysis of the thread. A thread with none is refused."""
    binding = await bound_conversation_analysis(conversation_id=conversation_id)
    if binding is None:
        msg = (
            "This thread has no open EDA analysis, so there is nothing to "
            "compute on. Call open_eda_analysis first."
        )
        raise ValueError(msg)
    entry, study = await get_study_detail_for_dataset(
        binding.site_id, binding.dataset_id
    )
    analysis = await read_analysis(binding.site_id, analysis_id=binding.analysis_id)
    return BoundStudy(binding=binding, entry=entry, study=study, analysis=analysis)


async def append_part(*, conversation_id: UUID, chunk: DataChunk) -> None:
    await append_chunk(
        conversation_id=conversation_id,
        chunk=chunk.model_dump(by_alias=True, mode="json", exclude_none=True),
    )


async def announce_analysis(
    *, conversation_id: UUID, bound: BoundStudy, analysis: EdaAnalysisDetail
) -> None:
    """Put the mutated analysis on the thread, under a fresh revision."""
    revision = await bump_analysis_revision(conversation_id=conversation_id)
    state = await analysis_state(
        site_id=bound.binding.site_id,
        dataset_id=bound.binding.dataset_id,
        entry=permission_facts(bound.entry),
        study=bound.study,
        analysis=analysis,
        revision=revision,
    )
    await append_part(
        conversation_id=conversation_id, chunk=eda_analysis_state_chunk(state)
    )


__all__ = ["BoundStudy", "announce_analysis", "append_part", "bound_study"]
