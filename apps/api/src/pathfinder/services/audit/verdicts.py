"""Who calls an audit tool, and the verdicts a model stores in a conversation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict

from pathfinder.domain.audit.verdicts import (
    FindingReview,
    GeneModelVerdict,
    VerdictOrigin,
)
from pathfinder.domain.statistic_facts import Identifier
from pathfinder.persistence.repositories.audit_reviews import AuditReviewRepository
from pathfinder.platform.audit_errors import AuditNeedsAThreadError
from pathfinder.services.audit.runs import RunOwner


@dataclass(frozen=True, kw_only=True)
class AuditCaller:
    user_id: UUID
    conversation_id: UUID | None
    site_id: str

    def owner(self) -> RunOwner:
        if self.conversation_id is None:
            raise AuditNeedsAThreadError
        return RunOwner(user_id=self.user_id, conversation_id=self.conversation_id)


class VerdictView(CamelModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: Identifier
    run_id: UUID | None
    finding_id: int | None
    origin: VerdictOrigin
    verdict: GeneModelVerdict
    review: FindingReview | None
    created_at: datetime


async def record_verdict(
    *,
    caller: AuditCaller,
    origin: VerdictOrigin,
    verdict: GeneModelVerdict,
    model_id: str,
) -> int:
    async with async_session_factory() as session:
        verdict_id = await AuditReviewRepository(session).add_verdict(
            user_id=caller.user_id,
            conversation_id=caller.conversation_id,
            site_id=caller.site_id,
            origin=origin,
            verdict=verdict,
            model_id=model_id,
        )
        await session.commit()
    return verdict_id


async def conversation_verdicts(
    conversation_id: UUID, user_id: UUID
) -> list[VerdictView]:
    async with async_session_factory() as session:
        found = await AuditReviewRepository(session).of_conversation(
            conversation_id, user_id
        )
    return [VerdictView.model_validate(record) for record in found]
