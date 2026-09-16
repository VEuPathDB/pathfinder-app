"""Site sub-routers (catalog, params, genes, strategies)."""

from fastapi import APIRouter

from pathfinder.transport.http.routers.sites import catalog, genes, params, strategies

router = APIRouter()
router.include_router(catalog.router)
router.include_router(params.router)
router.include_router(genes.router)
router.include_router(strategies.router)
