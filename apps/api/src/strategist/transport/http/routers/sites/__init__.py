"""Site sub-routers (catalog, datasets, params, strategies)."""

from fastapi import APIRouter

from strategist.transport.http.routers.sites import (
    catalog,
    datasets,
    params,
    strategies,
)

router = APIRouter()
router.include_router(catalog.router)
router.include_router(datasets.router)
router.include_router(params.router)
router.include_router(strategies.router)
