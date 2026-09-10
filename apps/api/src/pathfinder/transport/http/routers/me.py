from __future__ import annotations

from assistant_core import quota
from fastapi import APIRouter

from pathfinder.services.eval_data.consent import (
    PrivacySettings,
    PrivacyUpdate,
    read_privacy,
    update_privacy,
)
from pathfinder.services.users import effective_monthly_limit_usd
from pathfinder.transport.http.deps import CurrentUser, DBSession
from pathfinder.transport.http.schemas.me import QuotaResponse

router = APIRouter(prefix="/api/v1/me", tags=["me"])


@router.get("/quota", response_model=QuotaResponse)
async def get_my_quota(session: DBSession, user_id: CurrentUser) -> QuotaResponse:
    q = await quota.get_current(
        session,
        user_id,
        limit_usd=await effective_monthly_limit_usd(session, user_id),
    )
    return QuotaResponse(
        used_usd=q.used_usd,
        limit_usd=q.limit_usd,
        total_tokens=q.total_tokens,
        percent=q.percent,
        resets_at=q.resets_at,
    )


@router.get("/privacy", response_model=PrivacySettings)
async def get_my_privacy(
    session: DBSession,
    user_id: CurrentUser,
) -> PrivacySettings:
    """Return the eval-data decision, and whether the notice was shown."""
    return await read_privacy(session, user_id)


@router.patch("/privacy", response_model=PrivacySettings)
async def patch_my_privacy(
    session: DBSession,
    user_id: CurrentUser,
    update: PrivacyUpdate,
) -> PrivacySettings:
    """Change the eval-data decision, the notice marker, or both.

    Turning consent off also clears the user's staged candidates.
    """
    return await update_privacy(session, user_id, update)
