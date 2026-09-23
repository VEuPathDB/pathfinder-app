"""WDK identity: who a request is on VEuPathDB, and the internal user it maps to.

VEuPathDB serves the WDK service to registered users only, so a WDK-backed
request carries the user's own token or it is refused.
"""

import hashlib
import time
from collections.abc import Awaitable
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from pydantic import BaseModel, ConfigDict
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import WDKError, WDKLoginRequiredError
from veupathdb.wdk import resolve_registered_email, validate_oauth_token

from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import (
    SiteUnavailableError,
    WDKIdentityMismatchError,
    site_failure_reason,
)
from pathfinder.platform.principal import Principal
from pathfinder.platform.readiness import get_readiness
from pathfinder.services.users import get_or_create_user_id

logger = get_logger(__name__)

_IDENTITY_CACHE_SECONDS = 300.0
_IDENTITY_CACHE_MAX_ENTRIES = 512


async def require_registered_wdk_login() -> None:
    """Refuse a request that names no registered VEuPathDB user.

    The signature is verified against the OAuth server's cached key, so a
    forged or expired token is refused and a guest one names nobody.
    """
    token = veupathdb_auth_token_ctx.get()
    if not token:
        raise WDKLoginRequiredError
    claims = await validate_oauth_token(token, get_settings().veupathdb_oauth_url)
    if claims is None or claims.is_guest:
        raise WDKLoginRequiredError


_identities: dict[str, tuple[float, UUID]] = {}


def identity_site(site_id: str) -> str:
    """Name the site an identity call reads for a request that names ``site_id``.

    The WDK user id is account scoped, so a loaded site answers the same user
    when the named one has no catalog and would answer nothing.
    """
    readiness = get_readiness()
    if readiness.degraded_catalog(site_id) is None:
        return site_id
    return readiness.first_ready_catalog or site_id


_SERVER_ERROR = 500


async def identity_or_unavailable[T](site_id: str, read: Awaitable[T]) -> T:
    """Await an identity read of ``site_id``, refusing the request on an outage.

    A server status means the site did not answer, so the refusal is a 503
    that names the site. A client status propagates unchanged.
    """
    try:
        return await read
    except WDKError as error:
        if error.status < _SERVER_ERROR:
            raise
        reason = site_failure_reason(error.__cause__ or error)
        raise SiteUnavailableError(site_id, reason) from error


async def resolve_veupathdb_user_id(token: str, site_id: str) -> UUID | None:
    """Map a VEuPathDB token to the internal user, by the email WDK reports.

    None when the site refuses the token or names a guest. The mapping is
    remembered per token for a few minutes, so a bearer client does not cost a
    WDK round trip on every request.
    """
    site_id = identity_site(site_id)
    key = hashlib.sha256(f"{site_id}\0{token}".encode()).hexdigest()
    cached = _identities.get(key)
    if cached is not None and cached[0] > time.monotonic():
        return cached[1]

    email = await identity_or_unavailable(
        site_id, resolve_registered_email(token, site_id)
    )
    if not email:
        return None

    async with async_session_factory() as session:
        user_id = await get_or_create_user_id(session, email)
        await session.commit()

    if len(_identities) >= _IDENTITY_CACHE_MAX_ENTRIES:
        _identities.clear()
    _identities[key] = (time.monotonic() + _IDENTITY_CACHE_SECONDS, user_id)
    return user_id


async def require_session_matches_wdk_identity(
    principal: Principal, site_id: str
) -> None:
    """Refuse a request whose VEuPathDB token names another internal user.

    ``site_id`` is the site the request names, so the check reads the account
    on a site this process can reach. A token the site refuses names no
    registered user and is a login refusal; a site that does not answer is a
    503. A dev-login session is a synthetic user with no VEuPathDB account, so
    it acts as whatever token it carries.
    """
    if principal.credential == "dev-login":
        return
    token = veupathdb_auth_token_ctx.get()
    if not token:
        raise WDKLoginRequiredError
    token_user_id = await resolve_veupathdb_user_id(token, site_id)
    if token_user_id is None:
        raise WDKLoginRequiredError
    if token_user_id != principal.user_id:
        raise WDKIdentityMismatchError


class VEuPathDBBearer(BaseModel):
    """What a VEuPathDB bearer token proves. ``rejection`` says why it proves nothing."""

    model_config = ConfigDict(frozen=True)

    user_id: UUID | None = None
    rejection: str = ""


async def resolve_veupathdb_bearer(token: str) -> VEuPathDBBearer:
    """Verify a VEuPathDB bearer token and name the internal user it belongs to.

    Only registered users are accepted: a guest token names nobody durable.
    """
    settings = get_settings()
    claims = await validate_oauth_token(token, settings.veupathdb_oauth_url)
    if claims is None:
        return VEuPathDBBearer(rejection="Invalid VEuPathDB token")
    if claims.is_guest:
        return VEuPathDBBearer(rejection="A guest VEuPathDB token cannot sign in")

    user_id = await resolve_veupathdb_user_id(token, settings.veupathdb_default_site)
    if user_id is None:
        return VEuPathDBBearer(rejection="VEuPathDB session expired or invalid")
    return VEuPathDBBearer(user_id=user_id)
