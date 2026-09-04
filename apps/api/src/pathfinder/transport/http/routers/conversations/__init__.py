"""Conversations router (composed by responsibility)."""

from fastapi import APIRouter, Depends

from pathfinder.transport.http.deps import require_registered_wdk_identity

from . import (
    cancel,
    counts,
    crud,
    events,
    insert_saved,
    operations,
    revert,
    save_substrategy,
    scratchpad,
    sidebar,
    wdk_import,
)

# Subroutes whose every request reads or writes WDK-owned resources
# (strategies, steps) in the user's own VEuPathDB account. The routes that
# reach WDK on only one of their paths carry the gate on the route itself.
_WDK_BACKED = (
    counts.router,
    operations.router,
    wdk_import.router,
    insert_saved.router,
)

router = APIRouter()
router.include_router(crud.router)
router.include_router(events.router)
router.include_router(sidebar.router)
router.include_router(scratchpad.router)
router.include_router(revert.router)
router.include_router(save_substrategy.router)
router.include_router(cancel.router)
for wdk_router in _WDK_BACKED:
    router.include_router(
        wdk_router,
        dependencies=[Depends(require_registered_wdk_identity)],
    )
