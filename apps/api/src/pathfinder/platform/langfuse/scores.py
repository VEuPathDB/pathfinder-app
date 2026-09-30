"""A researcher's rating of one assistant message, as a Langfuse score."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pathfinder.platform.langfuse.client import get_langfuse

_VALUES = {"like": 1, "dislike": -1, None: 0}


class RatingScore(BaseModel):
    """The rating a message holds now; ``None`` is a rating taken back."""

    model_config = ConfigDict(frozen=True)

    message_id: UUID
    conversation_id: UUID
    trace_id: str | None
    rating: Literal["like", "dislike"] | None
    metadata: dict[str, str | int | float] = Field(default_factory=dict)


def record_rating(score: RatingScore) -> None:
    """Score the turn's trace, or its session when the turn has no trace.

    One score id per message, so the latest rating replaces the earlier one.
    """
    client = get_langfuse()
    if client is None:
        return
    client.create_score(
        score_id=f"rating-{score.message_id}",
        name="rating",
        value=_VALUES[score.rating],
        data_type="NUMERIC",
        comment=score.rating or "cleared",
        trace_id=score.trace_id,
        session_id=None if score.trace_id else str(score.conversation_id),
        metadata={"message_id": str(score.message_id), **score.metadata},
    )
