from __future__ import annotations

from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from fastapi import APIRouter
from pydantic import ConfigDict

from pathfinder.services.conversations.account_reads import (
    AccountReads,
    set_account_reads,
)
from pathfinder.transport.http.deps import CurrentUser, DBSession

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


class AccountReadsRequest(CamelModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool


@router.put(
    "/{conversation_id}/account-reads",
    response_model=AccountReads,
    summary="Allow or refuse Explore's reads of the researcher's account in this thread.",
)
async def put_account_reads(
    conversation_id: UUID,
    body: AccountReadsRequest,
    session: DBSession,
    user_id: CurrentUser,
) -> AccountReads:
    return await set_account_reads(
        session, conversation_id=conversation_id, user_id=user_id, allowed=body.allowed
    )
