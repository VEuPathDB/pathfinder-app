"""HTTP routes for the EDA tab. Every route calls services only."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from assistant_core.conversation.authz import assert_owner
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.services.eda.binding import (
    bind_analysis,
    bound_conversation_analysis,
    bound_or_conflict,
    mutated_analysis_state,
    read_analysis,
    read_analysis_state,
    unbind_conversation_analysis,
)
from pathfinder.services.eda.catalog import browse_studies, search_studies
from pathfinder.services.eda.compute import (
    analysis_comparison,
    bound_volcano,
    stored_volcano_cut,
)
from pathfinder.services.eda.steps import export_analysis_step
from pathfinder.transport.http.deps import (
    AvailableSite,
    CurrentUser,
    DBSession,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.schemas.eda import (
    ConversationEdaPatchRequest,
    ConversationEdaResponse,
    EdaAnalysisPatchResponse,
    EdaBindAction,
    EdaExportStepAction,
    EdaStudyListResponse,
    EdaStudySummaryResponse,
    EdaUnbindAction,
    EdaVizPointResponse,
    EdaVizRequest,
    EdaVizResponse,
)

studies_router = APIRouter(prefix="/api/v1/eda", tags=["eda"])
conversation_router = APIRouter(prefix="/api/v1/conversations", tags=["eda"])

_DEFAULT_STUDY_LIMIT = 20


@studies_router.get("/studies", response_model=EdaStudyListResponse)
async def list_eda_studies(
    site_id: AvailableSite,
    user_id: CurrentUser,
    q: Annotated[str, Query(max_length=500)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = _DEFAULT_STUDY_LIMIT,
) -> EdaStudyListResponse:
    """Search the studies this account can see, or list them when q is empty."""
    del user_id
    cards = (
        (await search_studies(site_id, q, limit=limit)).cards
        if q
        else await browse_studies(site_id, limit=limit)
    )
    return EdaStudyListResponse(
        studies=[
            EdaStudySummaryResponse.model_validate(card, from_attributes=True)
            for card in cards
        ],
    )


@studies_router.post("/viz", response_model=EdaVizResponse)
async def read_eda_viz(
    request: EdaVizRequest,
    site_id: AvailableSite,
    conversation_id: Annotated[UUID, Query(alias="conversationId")],
    session: DBSession,
    user_id: CurrentUser,
) -> EdaVizResponse:
    """The bound analysis's volcano under the cut it stores. It starts no compute.

    ``site_id`` gates the route on the page's site; the volcano is read on the
    site the analysis is bound to.
    """
    del site_id
    await assert_owner(session, conversation_id, user_id)
    bound = await bound_or_conflict(conversation_id=conversation_id)
    analysis = await read_analysis(bound.site_id, analysis_id=bound.analysis_id)
    thresholds = stored_volcano_cut(analysis)
    view = await bound_volcano(
        bound.site_id,
        dataset_id=bound.dataset_id,
        analysis=analysis,
        thresholds=thresholds,
    )
    return EdaVizResponse(
        chart=request.chart,
        effect_size_label=view.effect_size_label,
        effect_size_threshold=thresholds.effect_size_threshold,
        significance_threshold=thresholds.significance_threshold,
        effect_direction=thresholds.effect_direction,
        total_points=view.total_points,
        retained_points=view.retained_points,
        retained_point_ids=view.retained_point_ids,
        points=[
            EdaVizPointResponse.model_validate(point, from_attributes=True)
            for point in view.points
        ],
        comparison=analysis_comparison(analysis),
    )


@conversation_router.get(
    "/{conversation_id}/eda", response_model=ConversationEdaResponse
)
async def get_conversation_eda(
    conversation_id: UUID,
    session: DBSession,
    user_id: CurrentUser,
) -> ConversationEdaResponse:
    """The analysis this conversation has open, read from the site on every call."""
    await assert_owner(session, conversation_id, user_id)
    bound = await bound_conversation_analysis(conversation_id=conversation_id)
    if bound is None:
        return ConversationEdaResponse(analysis=None)
    analysis = await read_analysis(bound.site_id, analysis_id=bound.analysis_id)
    return ConversationEdaResponse(
        analysis=await read_analysis_state(bound=bound, analysis=analysis),
    )


@conversation_router.patch(
    "/{conversation_id}/eda", response_model=EdaAnalysisPatchResponse
)
async def patch_conversation_eda(
    conversation_id: UUID,
    body: ConversationEdaPatchRequest,
    session: DBSession,
    user_id: CurrentUser,
) -> EdaAnalysisPatchResponse:
    """Bind a study, export the analysis as a step, or unbind."""
    await assert_owner(session, conversation_id, user_id)
    match body:
        case EdaBindAction():
            return await _bind(conversation_id, body)
        case EdaExportStepAction():
            return await _export_step(session, conversation_id, user_id, body)
        case EdaUnbindAction():
            return await _unbind(conversation_id)


async def _bind(
    conversation_id: UUID,
    body: EdaBindAction,
) -> EdaAnalysisPatchResponse:
    state = await bind_analysis(
        body.site_id,
        dataset_id=body.dataset_id,
        conversation_id=conversation_id,
        display_name=body.purpose,
    )
    return EdaAnalysisPatchResponse(analysis=state, step=None)


async def _export_step(
    session: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
    body: EdaExportStepAction,
) -> EdaAnalysisPatchResponse:
    step = await export_analysis_step(
        session=session,
        conversation_id=conversation_id,
        user_id=user_id,
        reads_the_volcano=body.source == "volcano",
    )
    return EdaAnalysisPatchResponse(
        analysis=await mutated_analysis_state(conversation_id=conversation_id),
        step=step,
    )


async def _unbind(conversation_id: UUID) -> EdaAnalysisPatchResponse:
    """Clear the binding. Unbinding an unbound thread is the same answer."""
    await unbind_conversation_analysis(conversation_id=conversation_id)
    return EdaAnalysisPatchResponse(analysis=None, step=None)


# Every EDA route reads a VEuPathDB account, so the gate is on the composed
# router rather than per route.
router = APIRouter()
for eda_router in (studies_router, conversation_router):
    router.include_router(
        eda_router,
        dependencies=[Depends(require_registered_wdk_identity)],
    )
