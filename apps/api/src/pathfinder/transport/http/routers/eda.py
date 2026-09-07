"""HTTP routes for the EDA tab. Every route calls services only."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.eda_parts import EdaDistributionSeries
from pathfinder.services.conversations.authz import assert_owner
from pathfinder.services.eda.authoring import variable_distribution, verified_count
from pathfinder.services.eda.binding import (
    apply_filters,
    bind_analysis,
    bound_conversation_analysis,
    bound_or_conflict,
    mutated_analysis_state,
    read_analysis,
    read_analysis_state,
    unbind_conversation_analysis,
)
from pathfinder.services.eda.catalog import (
    browse_studies,
    get_study_detail_for_dataset,
    search_studies,
)
from pathfinder.services.eda.compute import (
    VolcanoThresholds,
    bound_volcano,
    run_analysis_compute,
)
from pathfinder.services.eda.description import describe_study, permission_facts
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
    EdaCountRequest,
    EdaCountResponse,
    EdaDistributionRequest,
    EdaExportStepAction,
    EdaJobRefResponse,
    EdaRunComputeAction,
    EdaSetFiltersAction,
    EdaStudyDetailResponse,
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


@studies_router.get("/studies/{dataset_id}", response_model=EdaStudyDetailResponse)
async def get_eda_study(
    dataset_id: str,
    site_id: AvailableSite,
    user_id: CurrentUser,
    entity_id: Annotated[str | None, Query(alias="entityId")] = None,
) -> EdaStudyDetailResponse:
    """One study's entity tree, and one entity's variables when named."""
    del user_id
    entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    described = describe_study(
        permission_facts(entry),
        study,
        dataset_id=dataset_id,
        entity_id=entity_id,
    )
    return EdaStudyDetailResponse.model_validate(described, from_attributes=True)


@studies_router.post("/count", response_model=EdaCountResponse)
async def count_eda_subset(
    request: EdaCountRequest,
    site_id: AvailableSite,
    user_id: CurrentUser,
) -> EdaCountResponse:
    """The subset's size on one entity, against that entity's whole size."""
    del user_id
    counted = await verified_count(
        site_id,
        dataset_id=request.dataset_id,
        entity_id=request.entity_id,
        filters=request.filters,
    )
    return EdaCountResponse.model_validate(counted, from_attributes=True)


@studies_router.post("/distribution", response_model=EdaDistributionSeries)
async def read_eda_distribution(
    request: EdaDistributionRequest,
    site_id: AvailableSite,
    user_id: CurrentUser,
) -> EdaDistributionSeries:
    """One variable's histogram under the subset the request names."""
    del user_id
    return await variable_distribution(
        site_id,
        dataset_id=request.dataset_id,
        entity_id=request.entity_id,
        variable_id=request.variable_id,
        filters=request.filters,
    )


@studies_router.post("/viz", response_model=EdaVizResponse)
async def read_eda_viz(
    request: EdaVizRequest,
    site_id: AvailableSite,
    conversation_id: Annotated[UUID, Query(alias="conversationId")],
    session: DBSession,
    user_id: CurrentUser,
) -> EdaVizResponse:
    """The bound analysis's volcano under one cut. It starts no compute."""
    await assert_owner(session, conversation_id, user_id)
    bound = await bound_or_conflict(conversation_id=conversation_id)
    analysis = await read_analysis(bound.site_id, analysis_id=bound.analysis_id)
    thresholds = VolcanoThresholds(
        effect_size_threshold=request.effect_size_threshold,
        significance_threshold=request.significance_threshold,
        effect_direction=request.effect_direction,
    )
    view = await bound_volcano(
        site_id,
        dataset_id=request.dataset_id,
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
        points=[
            EdaVizPointResponse.model_validate(point, from_attributes=True)
            for point in view.points
        ],
    )


@conversation_router.get(
    "/{conversation_id}/eda", response_model=ConversationEdaResponse
)
async def get_conversation_eda(
    conversation_id: UUID,
    session: DBSession,
    user_id: CurrentUser,
) -> ConversationEdaResponse:
    """The analysis this thread has open, with the upstream descriptor."""
    await assert_owner(session, conversation_id, user_id)
    bound = await bound_conversation_analysis(conversation_id=conversation_id)
    if bound is None:
        return ConversationEdaResponse(analysis=None, descriptor=None)
    analysis = await read_analysis(bound.site_id, analysis_id=bound.analysis_id)
    return ConversationEdaResponse(
        analysis=await read_analysis_state(bound=bound, analysis=analysis),
        descriptor=analysis.descriptor.model_dump(by_alias=True, mode="json"),
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
    """Mutate the thread's bound analysis: bind, subset, compute, export, unbind."""
    await assert_owner(session, conversation_id, user_id)
    match body:
        case EdaBindAction():
            return await _bind(conversation_id, body)
        case EdaSetFiltersAction():
            return await _set_filters(conversation_id, body)
        case EdaRunComputeAction():
            return await _run_compute(conversation_id, body)
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
    return EdaAnalysisPatchResponse(analysis=state, job=None, step=None)


async def _set_filters(
    conversation_id: UUID,
    body: EdaSetFiltersAction,
) -> EdaAnalysisPatchResponse:
    bound = await bound_or_conflict(conversation_id=conversation_id)
    state = await apply_filters(
        bound.site_id,
        conversation_id=conversation_id,
        dataset_id=bound.dataset_id,
        analysis_id=bound.analysis_id,
        filters=body.filters,
    )
    return EdaAnalysisPatchResponse(analysis=state, job=None, step=None)


async def _run_compute(
    conversation_id: UUID,
    body: EdaRunComputeAction,
) -> EdaAnalysisPatchResponse:
    bound = await bound_or_conflict(conversation_id=conversation_id)
    job = await run_analysis_compute(
        bound.site_id,
        analysis_id=bound.analysis_id,
        dataset_id=bound.dataset_id,
        computation=body.computation,
    )
    return EdaAnalysisPatchResponse(
        analysis=await mutated_analysis_state(conversation_id=conversation_id),
        job=EdaJobRefResponse(
            job_id=job.job_id,
            task_id=None,
            app_name=body.computation.type,
            status=job.status,
        ),
        step=None,
    )


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
        thresholds=body.thresholds,
    )
    return EdaAnalysisPatchResponse(
        analysis=await mutated_analysis_state(conversation_id=conversation_id),
        job=None,
        step=step,
    )


async def _unbind(conversation_id: UUID) -> EdaAnalysisPatchResponse:
    """Clear the binding. Unbinding an unbound thread is the same answer."""
    await unbind_conversation_analysis(conversation_id=conversation_id)
    return EdaAnalysisPatchResponse(analysis=None, job=None, step=None)


# Every EDA route reads a VEuPathDB account, so the gate is on the composed
# router rather than per route.
router = APIRouter()
for eda_router in (studies_router, conversation_router):
    router.include_router(
        eda_router,
        dependencies=[Depends(require_registered_wdk_identity)],
    )
