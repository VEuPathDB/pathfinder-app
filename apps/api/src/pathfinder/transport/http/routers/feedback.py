"""Product action endpoint. Records non-score user actions in Langfuse."""

from fastapi import APIRouter, Request, Response

from pathfinder.platform.langfuse.actions import (
    ProductActionEvent,
    record_product_action,
)
from pathfinder.platform.security import limiter
from pathfinder.transport.http.schemas.product_actions import ProductActionRequest

router = APIRouter(prefix="/api/v1", tags=["feedback"])


@router.post("/feedback/actions", status_code=204, response_class=Response)
@limiter.limit("120/minute")
async def submit_product_action(
    request: Request,
    body: ProductActionRequest,
) -> Response:
    """Record a non-score product action in Langfuse."""
    del request
    record_product_action(
        ProductActionEvent(
            action=body.action,
            stream_id=body.stream_id,
            trace_id=body.trace_id,
            strategy_id=body.strategy_id,
            plan_id=body.plan_id,
            entry_id=body.entry_id,
            message_group_id=body.message_group_id,
            metadata=body.metadata,
        )
    )
    return Response(status_code=204)
