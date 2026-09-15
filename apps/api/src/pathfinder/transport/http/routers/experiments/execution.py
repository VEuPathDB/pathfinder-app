"""Experiment execution endpoints: create, batch, benchmark, seed."""

from collections.abc import AsyncIterator

from assistant_core.platform.logging import get_logger
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from pathfinder.platform.errors import sanitize_error_for_client
from pathfinder.platform.security import limiter
from pathfinder.services.experiment.seed import run_seed
from pathfinder.services.experiment.seed.types import SeedComplete, SeedEvent
from pathfinder.services.experiment.streaming import (
    BatchEvent,
    BenchmarkEvent,
    ExperimentEvent,
    stream_batch_experiment,
    stream_benchmark,
    stream_experiment,
)
from pathfinder.services.experiment.types import (
    BatchExperimentConfig,
    BatchOrganismTarget,
)
from pathfinder.transport.http.deps import (
    CurrentUser,
    DBSession,
    SiteIdQuery,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.schemas.experiments import (
    CreateBatchExperimentRequest,
    CreateBenchmarkRequest,
    CreateExperimentRequest,
)
from pathfinder.transport.http.sse_utils import (
    SSE_RESPONSES,
    typed_event_stream_response,
)

from ._config import config_from_request

# Every route here runs a search in the user's own VEuPathDB account.
router = APIRouter(dependencies=[Depends(require_registered_wdk_identity)])
logger = get_logger(__name__)


@router.post(
    "",
    responses=SSE_RESPONSES,
)
@limiter.limit("20/minute")
async def create_experiment(
    request: Request,
    body: CreateExperimentRequest,
    user_id: CurrentUser,
) -> StreamingResponse:
    """Create and run an experiment, streaming typed progress events directly."""
    config = await config_from_request(body, user_id)

    async def _producer() -> AsyncIterator[ExperimentEvent]:
        async for event in stream_experiment(config, user_id=str(user_id)):
            yield event

    return typed_event_stream_response(_producer(), event_name=lambda e: e.type)


@router.post(
    "/batch",
    responses=SSE_RESPONSES,
)
@limiter.limit("10/minute")
async def create_batch_experiment(
    request: Request,
    body: CreateBatchExperimentRequest,
    user_id: CurrentUser,
) -> StreamingResponse:
    """Run the same search across multiple organisms, streaming progress directly."""
    base_config = await config_from_request(body.base, user_id)
    batch_config = BatchExperimentConfig(
        base_config=base_config,
        organism_param_name=body.organism_param_name,
        target_organisms=[
            BatchOrganismTarget(
                organism=t.organism,
                positive_controls=t.positive_controls,
                negative_controls=t.negative_controls,
            )
            for t in body.target_organisms
        ],
    )

    async def _producer() -> AsyncIterator[BatchEvent]:
        async for event in stream_batch_experiment(batch_config, user_id=str(user_id)):
            yield event

    return typed_event_stream_response(_producer(), event_name=lambda e: e.type)


@router.post(
    "/benchmark",
    responses=SSE_RESPONSES,
)
@limiter.limit("10/minute")
async def create_benchmark(
    request: Request,
    body: CreateBenchmarkRequest,
    user_id: CurrentUser,
) -> StreamingResponse:
    """Run the same strategy against multiple control sets, streaming progress directly."""
    base_config = await config_from_request(body.base, user_id)
    control_sets = [
        (
            cs.label,
            cs.positive_controls,
            cs.negative_controls,
            cs.control_set_id,
            cs.is_primary,
        )
        for cs in body.control_sets
    ]
    has_primary = any(cs.is_primary for cs in body.control_sets)
    if not has_primary and control_sets:
        control_sets[0] = (
            control_sets[0][0],
            control_sets[0][1],
            control_sets[0][2],
            control_sets[0][3],
            True,
        )

    async def _producer() -> AsyncIterator[BenchmarkEvent]:
        async for event in stream_benchmark(
            base_config,
            control_sets,
            user_id=str(user_id),
        ):
            yield event

    return typed_event_stream_response(_producer(), event_name=lambda e: e.type)


@router.post(
    "/seed",
    responses=SSE_RESPONSES,
)
async def seed_strategies(
    user_id: CurrentUser,
    session: DBSession,
    site_id: SiteIdQuery = None,
) -> StreamingResponse:
    """Seed demo strategies and control sets across VEuPathDB sites.

    With a site id, only seeds for that database are created.
    """

    async def _producer() -> AsyncIterator[SeedEvent]:
        try:
            async for event in run_seed(
                user_id=user_id,
                session=session,
                site_id=site_id,
            ):
                yield event
        except Exception as exc:
            logger.exception("Seed failed", error=str(exc))
            yield SeedComplete(
                message="Seed failed",
                error=sanitize_error_for_client(exc),
            )

    return typed_event_stream_response(
        _producer(),
        event_name=lambda e: e.type,
    )
