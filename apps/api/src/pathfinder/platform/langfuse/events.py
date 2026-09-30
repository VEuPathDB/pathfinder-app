"""Product events: what a researcher did in the UI, on the conversation's session."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from assistant_core.platform.logging import get_logger
from langfuse import propagate_attributes
from opentelemetry import context
from pydantic import BaseModel, ConfigDict, Field

from pathfinder.platform.langfuse.client import get_langfuse

logger = get_logger(__name__)

ProductEventName = Literal[
    "card_answered",
    "strategy_opened",
    "export_requested",
    "turn_undone",
    "assistant_regenerated",
    "conversation_created",
    "site_switched",
]


class ProductEvent(BaseModel):
    """One event, the researcher who caused it, and the thread it belongs to."""

    model_config = ConfigDict(frozen=True)

    name: ProductEventName
    user_id: UUID
    conversation_id: UUID | None = None
    attributes: dict[str, str | int | bool] = Field(default_factory=dict)


def record_product_event(event: ProductEvent) -> None:
    """Record one event as a root observation on its session. Dropped without Langfuse."""
    client = get_langfuse()
    if client is None:
        return
    trace_name = f"product.{event.name}"
    session = None if event.conversation_id is None else str(event.conversation_id)
    # An empty context keeps the event out of the request span it was sent from.
    token = context.attach(context.Context())
    try:
        with propagate_attributes(
            user_id=str(event.user_id),
            session_id=session,
            trace_name=trace_name,
            tags=["product-event"],
        ):
            client.create_event(name=trace_name, metadata=event.attributes)
    finally:
        context.detach(token)
    logger.info("Product event recorded", product_event=event.name)
