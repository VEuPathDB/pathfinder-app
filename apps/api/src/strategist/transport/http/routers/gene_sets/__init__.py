"""Gene set HTTP endpoints. Business logic lives in ``services.gene_sets``."""

from fastapi import APIRouter

from . import crud, vdi

_PREFIX = "/api/v1/gene-sets"

router = APIRouter(tags=["gene-sets"])

# Include order is the order the published spec lists these paths in.
for _sub in (crud.router, vdi.router):
    router.include_router(_sub, prefix=_PREFIX)
