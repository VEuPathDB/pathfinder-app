"""The conversation-to-analysis binding, and the state both surfaces render."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from veupathdb.domain.eda_validation import find_gene_entity
from veupathdb.eda.factory import get_eda_analyses_client
from veupathdb.eda.models import (
    EdaAnalysisDetail,
    EdaFilter,
    EdaStudyDetail,
)

from pathfinder.domain.eda_parts import EdaAnalysisState
from pathfinder.persistence.models import ConversationAnalysisView
from pathfinder.persistence.repositories.conversation_analysis import (
    ConversationAnalysesRepository,
)
from pathfinder.platform.errors import AppError, ErrorCode
from pathfinder.services.eda.authoring import (
    open_analysis,
    patch_subset,
    resolve_eda_user_id,
    subset_entity_counts,
)
from pathfinder.services.eda.catalog import get_study_detail_for_dataset
from pathfinder.services.eda.description import (
    EdaPermissionFacts,
    display_names,
    filter_summaries,
    permission_facts,
)

_CONFLICT = 409

# The view is the read shape every caller of this module receives, so the
# module publishes it rather than sending tools into persistence.
__all__ = [
    "ConversationAnalysisView",
    "NoOpenAnalysisError",
    "analysis_state",
    "apply_filters",
    "bind_analysis",
    "bind_conversation_analysis",
    "bound_conversation_analysis",
    "bound_or_conflict",
    "bump_analysis_revision",
    "mutated_analysis_state",
    "open_analysis_or_conflict",
    "read_analysis",
    "read_analysis_state",
    "unbind_conversation_analysis",
]


class NoOpenAnalysisError(AppError):
    """The thread has no EDA analysis open, so there is nothing to act on."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            code=ErrorCode.EDA_NO_OPEN_ANALYSIS,
            title="No study is open",
            status=_CONFLICT,
            detail=detail,
        )


def _repo() -> ConversationAnalysesRepository:
    return ConversationAnalysesRepository(session_factory=async_session_factory)


async def bind_conversation_analysis(
    *,
    conversation_id: UUID,
    site_id: str,
    dataset_id: str,
    analysis_id: str,
) -> None:
    await _repo().bind(
        conversation_id=conversation_id,
        site_id=site_id,
        dataset_id=dataset_id,
        analysis_id=analysis_id,
    )


async def bound_conversation_analysis(
    *,
    conversation_id: UUID,
) -> ConversationAnalysisView | None:
    return await _repo().get(conversation_id=conversation_id)


async def bump_analysis_revision(*, conversation_id: UUID) -> int:
    """Count one authoring mutation. Returns 0 when no analysis is open."""
    return await _repo().increment(conversation_id=conversation_id)


async def unbind_conversation_analysis(*, conversation_id: UUID) -> None:
    await _repo().unbind(conversation_id=conversation_id)


async def read_analysis(site_id: str, *, analysis_id: str) -> EdaAnalysisDetail:
    """The upstream document. It is the SSOT, so every render reads it."""
    analyses = get_eda_analyses_client(site_id)
    return await analyses.get(
        user_id=await resolve_eda_user_id(site_id),
        analysis_id=analysis_id,
    )


async def analysis_state(
    *,
    site_id: str,
    dataset_id: str,
    entry: EdaPermissionFacts,
    study: EdaStudyDetail,
    analysis: EdaAnalysisDetail,
    revision: int,
) -> EdaAnalysisState:
    """The open analysis, as both surfaces re-render it after every mutation.

    ``revision`` counts the mutations of the binding, so the two surfaces
    order their writes on it. The counts belong to the subset the analysis
    holds. Rows export only when the account may read them and the study
    names exactly one gene entity.
    """
    gene = find_gene_entity(study, subject="strategy step")
    return EdaAnalysisState(
        site_id=site_id,
        dataset_id=dataset_id,
        study_id=study.id,
        analysis_id=analysis.analysis_id,
        revision=revision,
        study_display_name=entry.display_name,
        display_name=analysis.display_name,
        num_filters=analysis.num_filters,
        num_computations=analysis.num_computations,
        filters=[
            entry_filter.model_dump(by_alias=True, mode="json", exclude_none=True)
            for entry_filter in analysis.descriptor.subset.descriptor
        ],
        filter_summaries=filter_summaries(
            analysis.descriptor.subset.descriptor,
            display_names=display_names(study),
        ),
        entity_counts=await subset_entity_counts(
            site_id, study=study, filters=analysis.descriptor.subset.descriptor
        ),
        can_export_rows=entry.can_export_rows and gene.entity_id is not None,
    )


async def bind_analysis(
    site_id: str,
    *,
    dataset_id: str,
    conversation_id: UUID,
    display_name: str,
) -> EdaAnalysisState:
    """Open an analysis on a study and bind it to this thread.

    A thread holds one analysis at a time, so this replaces whatever it had
    open and restarts the revision.
    """
    entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    analysis_id = await open_analysis(
        site_id, dataset_id=dataset_id, display_name=display_name
    )
    await bind_conversation_analysis(
        conversation_id=conversation_id,
        site_id=site_id,
        dataset_id=dataset_id,
        analysis_id=analysis_id,
    )
    revision = await bump_analysis_revision(conversation_id=conversation_id)
    return await analysis_state(
        site_id=site_id,
        dataset_id=dataset_id,
        entry=permission_facts(entry),
        study=study,
        analysis=await read_analysis(site_id, analysis_id=analysis_id),
        revision=revision,
    )


async def bound_or_conflict(*, conversation_id: UUID) -> ConversationAnalysisView:
    """The thread's binding, or the conflict that names what is missing."""
    bound = await bound_conversation_analysis(conversation_id=conversation_id)
    if bound is None:
        msg = (
            "This conversation has no study open, so it has no subset and no "
            "comparison to act on. Open one first."
        )
        raise NoOpenAnalysisError(msg)
    return bound


async def open_analysis_or_conflict(
    *,
    conversation_id: UUID,
) -> tuple[ConversationAnalysisView, EdaAnalysisDetail]:
    """The thread's binding and its upstream document, or the conflict."""
    bound = await bound_or_conflict(conversation_id=conversation_id)
    return bound, await read_analysis(bound.site_id, analysis_id=bound.analysis_id)


async def apply_filters(
    site_id: str,
    *,
    conversation_id: UUID,
    dataset_id: str,
    analysis_id: str,
    filters: Sequence[EdaFilter],
) -> EdaAnalysisState:
    """Replace the analysis's subset and report the state both surfaces render.

    The array replaces the subset; it is not a patch.
    """
    analysis = await patch_subset(
        site_id,
        analysis_id=analysis_id,
        dataset_id=dataset_id,
        filters=filters,
    )
    revision = await bump_analysis_revision(conversation_id=conversation_id)
    entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    return await analysis_state(
        site_id=site_id,
        dataset_id=dataset_id,
        entry=permission_facts(entry),
        study=study,
        analysis=analysis,
        revision=revision,
    )


async def _state_of(
    bound: ConversationAnalysisView,
    analysis: EdaAnalysisDetail,
    revision: int,
) -> EdaAnalysisState:
    entry, study = await get_study_detail_for_dataset(bound.site_id, bound.dataset_id)
    return await analysis_state(
        site_id=bound.site_id,
        dataset_id=bound.dataset_id,
        entry=permission_facts(entry),
        study=study,
        analysis=analysis,
        revision=revision,
    )


async def read_analysis_state(
    *,
    bound: ConversationAnalysisView,
    analysis: EdaAnalysisDetail,
) -> EdaAnalysisState:
    """The state of an analysis already read, at the binding's own revision.

    Reading is not a mutation, so the counter does not move.
    """
    return await _state_of(bound, analysis, bound.revision)


async def mutated_analysis_state(*, conversation_id: UUID) -> EdaAnalysisState:
    """Count one mutation and report the state both surfaces re-render from."""
    bound, analysis = await open_analysis_or_conflict(conversation_id=conversation_id)
    revision = await bump_analysis_revision(conversation_id=conversation_id)
    return await _state_of(bound, analysis, revision)
