"""Dependency injection for HTTP routes."""

from typing import Annotated
from uuid import UUID

from assistant_core.platform.db import get_db_session
from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

import pathfinder.services.quota
from pathfinder.platform.errors import ForbiddenError, NotFoundError
from pathfinder.platform.principal import Principal
from pathfinder.platform.security import resolve_principal
from pathfinder.services.experiment.store import get_experiment_store
from pathfinder.services.experiment.types import Experiment
from pathfinder.services.users import ensure_user_exists
from pathfinder.services.wdk_identity import (
    require_registered_wdk_login,
    require_session_matches_wdk_identity,
)
from pathfinder.transport.http.schemas.site_id import SiteId

# Type aliases for dependencies
DBSession = Annotated[AsyncSession, Depends(get_db_session)]

# Optional ``siteId`` query param shared by list endpoints.
SiteIdQuery = Annotated[SiteId | None, Query(alias="siteId")]

# Required ``siteId`` query param for endpoints that write with it.
RequiredSiteIdQuery = Annotated[SiteId, Query(alias="siteId")]


async def get_current_principal_with_db_row(
    principal: Annotated[Principal, Depends(resolve_principal)],
    session: DBSession,
) -> Principal:
    """Ensure authenticated users exist in the local DB.

    We persist user IDs because many tables have a FK to `users.id`. Without this,
    first-time sessions can trigger integrity errors that bubble up as 500s.
    """
    await ensure_user_exists(session, principal.user_id)
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal_with_db_row)]


async def get_current_user_with_db_row(principal: CurrentPrincipal) -> UUID:
    """Return the authenticated user's ID."""
    return principal.user_id


CurrentUser = Annotated[UUID, Depends(get_current_user_with_db_row)]


async def require_registered_wdk_identity(principal: CurrentPrincipal) -> UUID:
    """Refuse a request that acts on WDK without a registered VEuPathDB login.

    Routes that read or write a WDK account attach this. The token must also
    name the session's own user, so one session writes to one WDK account.
    """
    await require_registered_wdk_login()
    await require_session_matches_wdk_identity(principal)
    return principal.user_id


async def require_quota_available(
    session: DBSession,
    user_id: CurrentUser,
) -> UUID:
    quota = await pathfinder.services.quota.check_allowed(session, user_id)
    if quota.used_usd >= quota.limit_usd:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "monthly_quota_exhausted",
                "usedUsd": str(quota.used_usd),
                "limitUsd": str(quota.limit_usd),
                "resetsAt": quota.resets_at.isoformat(),
                "totalTokens": quota.total_tokens,
            },
        )
    return user_id


QuotaCheckedUser = Annotated[UUID, Depends(require_quota_available)]


async def get_experiment_owned_by_user(
    experiment_id: str,
    user_id: CurrentUser,
) -> Experiment:
    """Resolve an experiment by ID and verify the current user owns it."""
    store = get_experiment_store()
    exp = await store.aget(experiment_id)
    if not exp:
        raise NotFoundError(title="Experiment not found")
    if exp.user_id != str(user_id):
        raise ForbiddenError(title="Not authorized to access this experiment")
    return exp


ExperimentDep = Annotated[Experiment, Depends(get_experiment_owned_by_user)]
