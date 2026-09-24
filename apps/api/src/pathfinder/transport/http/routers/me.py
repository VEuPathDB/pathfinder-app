from __future__ import annotations

from typing import Annotated, Any

from assistant_core import quota
from assistant_core.platform.types import PaidBy
from fastapi import APIRouter, Depends, Request, Response, status

from pathfinder.ai.models.catalog import get_smallest_model
from pathfinder.domain.provider_keys import KeyableProvider
from pathfinder.platform.errors import ForbiddenError, ProviderKeysDisabledError
from pathfinder.platform.identity import PATHFINDER_APPLICATION_ID
from pathfinder.platform.model_keys import KeyProbe, probe_key
from pathfinder.platform.principal import Principal
from pathfinder.platform.security import limiter
from pathfinder.services.eval_data.consent import (
    PrivacySettings,
    PrivacyUpdate,
    read_privacy,
    update_privacy,
)
from pathfinder.services.provider_keys import (
    ProviderKeyView,
    key_statuses,
    keys_enabled,
    list_keys,
    payers,
    revoke_key,
    store_key,
)
from pathfinder.services.users import effective_monthly_limit_usd
from pathfinder.transport.http.deps import CurrentPrincipal, CurrentUser, DBSession
from pathfinder.transport.http.schemas.me import (
    ProviderKeyIn,
    ProviderKeysResponse,
    QuotaResponse,
)

router = APIRouter(prefix="/api/v1/me", tags=["me"])

_PROBLEM = {
    "application/problem+json": {
        "schema": {"$ref": "#/components/schemas/ProblemDetail"}
    }
}
# Every key route refuses a calling application that is not PathFinder, and
# storing a key is refused where the deployment takes none.
_KEY_REFUSALS: dict[int | str, dict[str, Any]] = {
    403: {"description": "Forbidden", "content": _PROBLEM},
}
# Storing a key also meets the rate limit and a provider that did not answer
# the check.
_KEY_ENTRY_REFUSALS: dict[int | str, dict[str, Any]] = {
    **_KEY_REFUSALS,
    429: {"description": "Too Many Requests", "content": _PROBLEM},
    503: {"description": "Service Unavailable", "content": _PROBLEM},
}


@router.get("/quota", response_model=QuotaResponse)
async def get_my_quota(session: DBSession, user_id: CurrentUser) -> QuotaResponse:
    q = await quota.get_current(
        session,
        user_id,
        limit_usd=await effective_monthly_limit_usd(session, user_id),
    )
    own = await quota.get_period_totals(session, user_id, paid_by=PaidBy.USER)
    statuses = await key_statuses(session, user_id)
    return QuotaResponse(
        used_usd=q.used_usd,
        limit_usd=q.limit_usd,
        total_tokens=q.total_tokens,
        percent=q.percent,
        resets_at=q.resets_at,
        own_key_usd=own.cost_usd,
        own_key_tokens=own.tokens,
        own_key_providers=sorted(statuses.active),
    )


def key_probe() -> KeyProbe:
    """The check a new key passes before it is stored: one generation request."""
    return probe_key


async def researcher(principal: CurrentPrincipal) -> Principal:
    """A researcher's keys answer the application they were entered in, alone."""
    if principal.application_id != PATHFINDER_APPLICATION_ID:
        raise ForbiddenError(
            title="Provider keys belong to the researcher",
            detail="A calling application may not read or write provider keys.",
        )
    return principal


Researcher = Annotated[Principal, Depends(researcher)]


@router.get(
    "/provider-keys", response_model=ProviderKeysResponse, responses=_KEY_REFUSALS
)
async def get_my_provider_keys(
    session: DBSession, principal: Researcher
) -> ProviderKeysResponse:
    """The stored keys by their last four characters, and who pays for what."""
    statuses = await key_statuses(session, principal.user_id)
    return ProviderKeysResponse(
        enabled=keys_enabled(),
        keys=await list_keys(session, principal.user_id),
        payers=payers(statuses),
    )


@router.put(
    "/provider-keys/{provider}",
    response_model=ProviderKeyView,
    responses=_KEY_ENTRY_REFUSALS,
)
@limiter.limit("10/hour")
async def put_my_provider_key(
    request: Request,
    provider: KeyableProvider,
    body: ProviderKeyIn,
    session: DBSession,
    principal: Researcher,
    probe: Annotated[KeyProbe, Depends(key_probe)],
) -> ProviderKeyView:
    """Check the key with the provider, then store it sealed in place of the last.

    Each call spends on the key it names, so the route is rate limited.
    """
    del request
    if not keys_enabled():
        raise ProviderKeysDisabledError
    await probe(provider, get_smallest_model(provider).id, body.key)
    return await store_key(session, principal.user_id, provider, body.key)


@router.delete(
    "/provider-keys/{provider}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_KEY_REFUSALS,
)
async def delete_my_provider_key(
    provider: KeyableProvider, session: DBSession, principal: Researcher
) -> Response:
    """Revoke the key. Its ciphertext is dropped and it is never read again."""
    await revoke_key(session, principal.user_id, provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
