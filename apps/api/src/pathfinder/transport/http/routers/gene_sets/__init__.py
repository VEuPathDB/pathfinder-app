"""Gene set HTTP endpoints. Business logic lives in ``services.gene_sets``."""

from fastapi import APIRouter

from . import confidence, crud, enrichment, operations, records

_PREFIX = "/api/v1/gene-sets"

router = APIRouter(tags=["gene-sets"])

# Include order is the order the published spec lists these paths in.
for _sub in (
    crud.router,
    operations.router,
    enrichment.router,
    records.router,
    confidence.router,
):
    router.include_router(_sub, prefix=_PREFIX)
