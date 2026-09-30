"""One row per assistant turn: who ran it, where, when, and what it cost."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from assistant_core.persistence.models import Conversation, Message
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import User

__all__ = ["TurnUsageRow", "UsageReportRepository"]


class _Usage(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    total_tokens: int = Field(0, alias="totalTokens")
    cost_usd: Decimal = Field(Decimal(0), alias="costUsd")

    @field_validator("total_tokens", "cost_usd", mode="before")
    @classmethod
    def _an_unset_value_is_zero(cls, value: object) -> object:
        return 0 if value is None else value


class _TurnMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    usage: _Usage | None = None


_NO_USAGE = _Usage.model_validate({})


class TurnUsageRow(BaseModel):
    """One assistant turn's usage, with its thread and its researcher."""

    model_config = ConfigDict(frozen=True)

    conversation_id: UUID
    conversation_name: str
    site_id: str
    assistant_id: str
    user_id: UUID
    user_external_id: str | None
    created_at: datetime
    total_tokens: int
    cost_usd: Decimal


class UsageReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def turns(
        self, *, since: date | None = None, site_id: str | None = None
    ) -> list[TurnUsageRow]:
        """Every assistant turn from ``since`` on, oldest first, on one site or all."""
        query = (
            select(
                Message.conversation_id,
                Message.created_at,
                Message.metadata_,
                Conversation.name,
                Conversation.site_id,
                Conversation.assistant_id,
                Conversation.user_id,
                User.external_id,
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(User, User.id == Conversation.user_id)
            .where(Message.role == "assistant")
            .order_by(Message.created_at)
        )
        if since is not None:
            query = query.where(Message.created_at >= since)
        if site_id is not None:
            query = query.where(Conversation.site_id == site_id)
        rows = (await self._session.execute(query)).all()
        return [
            TurnUsageRow(
                conversation_id=row.conversation_id,
                conversation_name=row.name,
                site_id=row.site_id,
                assistant_id=row.assistant_id,
                user_id=row.user_id,
                user_external_id=row.external_id,
                created_at=row.created_at,
                total_tokens=usage.total_tokens,
                cost_usd=usage.cost_usd,
            )
            for row in rows
            for usage in (
                _TurnMetadata.model_validate(row.metadata_).usage or _NO_USAGE,
            )
        ]
