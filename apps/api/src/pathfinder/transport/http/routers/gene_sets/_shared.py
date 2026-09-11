"""The service handle, response mapping and error mapping every gene-set route uses."""

from typing import cast, get_args

from fastapi import Depends
from veupathdb_mcp.wdk import SetOperation

from pathfinder.platform.errors import NotFoundError
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.transport.http.deps import require_registered_wdk_identity
from pathfinder.transport.http.schemas.gene_sets import GeneSetResponse

# The routes that read or write the user's WDK account carry this; the ones
# that only touch the stored gene ids do not.
NEEDS_WDK_LOGIN = [Depends(require_registered_wdk_identity)]


def gene_set_service() -> GeneSetService:
    return GeneSetService(get_gene_set_store())


def to_response(gs: GeneSet) -> GeneSetResponse:
    valid_ops = get_args(SetOperation)
    operation: SetOperation | None = (
        cast("SetOperation", gs.operation) if gs.operation in valid_ops else None
    )
    return GeneSetResponse(
        id=gs.id,
        site_id=gs.site_id,
        name=gs.name,
        gene_ids=gs.gene_ids,
        source=gs.source,
        gene_count=len(gs.gene_ids),
        wdk_strategy_id=gs.wdk_strategy_id,
        wdk_step_id=gs.wdk_step_id,
        search_name=gs.search_name,
        record_type=gs.record_type,
        parameters=gs.parameters,
        parent_set_ids=gs.parent_set_ids,
        operation=operation,
        created_at=gs.created_at.isoformat(),
        step_count=gs.step_count,
        enrichment_results=gs.enrichment_results,
        vdi_id=gs.vdi_id,
    )


def not_found(exc: KeyError) -> NotFoundError:
    return NotFoundError(title=str(exc))


def no_strategy(exc: ValueError) -> NotFoundError:
    return NotFoundError(title="No WDK strategy", detail=str(exc))
