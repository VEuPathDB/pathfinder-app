"""The demo seed: strategies and control sets across VEuPathDB sites."""

from collections.abc import AsyncIterator

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from pathfinder.platform.errors import sanitize_error_for_client
from pathfinder.services.experiment.seed import run_seed
from pathfinder.services.experiment.seed.types import SeedComplete, SeedEvent
from pathfinder.transport.http.deps import (
    CurrentUser,
    SiteIdQuery,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.sse_utils import (
    SSE_RESPONSES,
    typed_event_stream_response,
)

# The seed builds strategies in the user's own VEuPathDB account.
router = APIRouter(
    prefix="/api/v1/seed",
    tags=["seed"],
    dependencies=[Depends(require_registered_wdk_identity)],
)
logger = get_logger(__name__)


@router.post("", responses=SSE_RESPONSES)
async def seed_strategies(
    user_id: CurrentUser,
    site_id: SiteIdQuery = None,
) -> StreamingResponse:
    """Seed demo strategies and control sets across VEuPathDB sites.

    With a site id, only seeds for that database are created.
    """

    async def _producer() -> AsyncIterator[SeedEvent]:
        try:
            async for event in run_seed(
                user_id=user_id,
                session_factory=async_session_factory,
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
