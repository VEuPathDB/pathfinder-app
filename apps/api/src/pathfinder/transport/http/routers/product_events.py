"""Product event ingress: what a researcher did in the UI, recorded in Langfuse."""

from typing import Annotated

from fastapi import APIRouter, Body, Request, Response

from pathfinder.platform.langfuse.events import ProductEvent, record_product_event
from pathfinder.platform.security import limiter
from pathfinder.transport.http.deps import CurrentUser
from pathfinder.transport.http.schemas.product_events import ProductEventRequest

router = APIRouter(prefix="/api/v1", tags=["product-events"])


@router.post("/product-events", status_code=204, response_class=Response)
@limiter.limit("120/minute")
async def record_event(
    request: Request,
    user_id: CurrentUser,
    body: Annotated[ProductEventRequest, Body()],
) -> Response:
    """Record one product event on the conversation's Langfuse session."""
    del request
    record_product_event(
        ProductEvent(
            name=body.event,
            user_id=user_id,
            conversation_id=body.conversation_id,
            attributes=body.model_dump(
                mode="json", exclude={"event", "conversation_id"}, exclude_none=True
            ),
        ),
    )
    return Response(status_code=204)
