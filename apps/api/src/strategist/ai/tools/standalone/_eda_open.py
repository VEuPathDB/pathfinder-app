from __future__ import annotations

from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.eda import EdaPermissionEntry

from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.domain.eda_thread import ConversationAnalysisView
from strategist.services.eda import EdaStudyDetail
from strategist.services.eda.binding import bound_conversation_analysis
from strategist.services.eda.catalog import (
    UnknownEdaDatasetError,
    get_study_detail_for_dataset,
)

NO_STUDY_OPEN = (
    "This conversation has no study open. Call open_eda_analysis on the dataset "
    "you want first."
)
FIND_A_DATASET = "Call search_eda_studies to find a real dataset id."


async def open_analysis(ctx: RunContext[LeadDeps]) -> ConversationAnalysisView:
    bound = await bound_conversation_analysis(
        conversation_id=ctx.deps.state.conversation_id
    )
    if bound is None:
        raise ModelRetry(NO_STUDY_OPEN)
    return bound


async def dataset_study(
    site_id: str, dataset_id: str
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    try:
        return await get_study_detail_for_dataset(site_id, dataset_id)
    except UnknownEdaDatasetError as exc:
        msg = f"{exc.guidance} {FIND_A_DATASET}"
        raise ModelRetry(msg) from exc


__all__ = ["FIND_A_DATASET", "NO_STUDY_OPEN", "dataset_study", "open_analysis"]
