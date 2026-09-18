"""User data management - purge endpoints.

Thin HTTP adapter; all business logic lives in
``pathfinder.services.user_data``.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from pathfinder.services.user_data import purge_user_data
from pathfinder.transport.http.deps import (
    CurrentUser,
    DBSession,
    MemoryStoreDep,
    SiteIdQuery,
)
from pathfinder.transport.http.schemas.user_data import (
    PurgeCounts,
    PurgeUserDataResponse,
)

router = APIRouter(prefix="/api/v1/user", tags=["user"])


@router.delete("/data", response_model=PurgeUserDataResponse)
async def purge_user_data_endpoint(
    user_id: CurrentUser,
    session: DBSession,
    memory_store: MemoryStoreDep,
    site_id: SiteIdQuery = None,
    *,
    delete_wdk: Annotated[bool, Query(alias="deleteWdk")] = False,
) -> PurgeUserDataResponse:
    """Purge user data from all local stores.

    When ``deleteWdk=false`` (default): every chat is **dismissed** (soft
    delete) so WDK sync won't re-import them; the strategies remain on
    VEuPathDB but PathFinder ignores them. Nothing is hard-deleted.

    When ``deleteWdk=true``: on VEuPathDB the strategies PathFinder created
    there are deleted, and everything whose strategy is gone is hard-deleted
    locally. A strategy the user made on the website stays. A chat whose
    strategy PathFinder could not delete - the site did not answer, the
    request names no registered VEuPathDB user, or the delete was refused -
    is dismissed instead of deleted, and a run in the same position keeps its
    row in the workbench, so a later purge can finish the job.
    ``wdkStrategiesKept`` counts those strategies.

    Always deletes: gene sets, control sets, the runs whose strategy is gone,
    and the user's investigations still waiting for curation. A staged
    investigation names a site, so a purge of one site clears only that
    site's; ``stagedEvalCases`` counts them.

    A memory names no site, so a purge of everything also deletes the user's
    memories and the tombstones that hold them out; a purge of one site
    leaves them.

    Pass ``?siteId=X`` to limit to one site, or omit for everything.
    """
    result = await purge_user_data(
        session=session,
        user_id=user_id,
        site_id=site_id,
        delete_wdk=delete_wdk,
        memory_store=memory_store,
    )

    return PurgeUserDataResponse(
        ok=True,
        deleted=PurgeCounts(
            strategies=result.hard_deleted + result.dismissed,
            wdk_strategies=result.wdk_strategies,
            wdk_strategies_kept=result.wdk_strategies_kept,
            memories=result.memories,
            gene_sets=result.gene_sets,
            experiments=result.experiments,
            control_sets=result.control_sets,
            staged_eval_cases=result.staged_eval_cases,
        ),
    )
