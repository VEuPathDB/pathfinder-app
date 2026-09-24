"""Site sub-routers (catalog, params, strategies)."""

from fastapi import APIRouter

from pathfinder.transport.http.routers.sites import catalog, params, strategies

router = APIRouter()
router.include_router(catalog.router)
router.include_router(params.router)
router.include_router(strategies.router)
