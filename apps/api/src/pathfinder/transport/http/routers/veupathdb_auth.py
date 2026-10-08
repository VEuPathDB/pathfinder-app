"""VEuPathDB login bridge. Links a VEuPathDB session to an internal user token."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import UnauthorizedError
from pathfinder.platform.security import (
    auth_cookie,
    clear_session_cookie,
    create_user_token,
    decode_session_token,
    decode_user_id,
    set_session_cookie,
)
from pathfinder.services.users import get_or_create_user_id
from pathfinder.services.wdk_identity import (
    current_user_on_a_site_that_answers,
    registered_email_on_a_site_that_answers,
)
from pathfinder.transport.http.deps import DBSession
from pathfinder.transport.http.schemas import (
    AuthStatusResponse,
    AuthSuccessResponse,
)
from pathfinder.transport.http.schemas.site_id import SiteId

router = APIRouter(prefix="/api/v1/veupathdb/auth", tags=["veupathdb-auth"])


async def _link_internal_user(
    session: AsyncSession, veupathdb_token: str, site_id: str
) -> UUID | None:
    """Name the internal user of the VEuPathDB identity, creating it if new."""
    email = await registered_email_on_a_site_that_answers(veupathdb_token, site_id)
    if not email:
        return None
    return await get_or_create_user_id(session, email)


@router.post("/refresh", response_model=AuthSuccessResponse)
async def refresh_internal_auth(
    request: Request,
    session: DBSession,
    existing: Annotated[str | None, Depends(auth_cookie)] = None,
    site_id: Annotated[SiteId, Query(alias="siteId")] = "veupathdb",
) -> JSONResponse:
    """Re-derive the internal auth token from a live VEuPathDB session.

    Use this when the internal token is absent or expired, and to relink a
    session whose VEuPathDB cookie now names another account. A dev-login
    session names no VEuPathDB account, so no token can move it.
    """
    claims = decode_session_token(existing) if existing else None
    if claims is not None and claims.dev_login:
        return JSONResponse({"success": True})
    session_user_id = None if claims is None else claims.user_id

    veupathdb_token = (
        request.headers.get("X-VEUPATHDB-AUTH")
        or request.headers.get("X-VEUPATHDB-AUTHORIZATION")
        or request.cookies.get("Authorization")
    )
    if not veupathdb_token:
        if session_user_id is not None:
            return JSONResponse({"success": True})
        raise UnauthorizedError(detail="No VEuPathDB session")

    internal_id = await _link_internal_user(session, veupathdb_token, site_id)
    if internal_id is None:
        if session_user_id is not None:
            return JSONResponse({"success": True})
        raise UnauthorizedError(detail="VEuPathDB session expired or invalid")
    if internal_id == session_user_id:
        return JSONResponse({"success": True})

    resp = JSONResponse({"success": True})
    set_session_cookie(resp, create_user_token(internal_id))
    return resp


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(
    response: Response,
    cookie_token: Annotated[str | None, Depends(auth_cookie)] = None,
    site_id: Annotated[SiteId, Query(alias="siteId")] = "veupathdb",
) -> AuthStatusResponse:
    """Return the current VEuPathDB auth status.

    A refused token or a guest is signed out, and a signed-out answer clears the
    PathFinder session; a site that does not answer is a 503. A mock chat
    provider has no VEuPathDB session, so the internal cookie alone proves
    identity there.
    """
    settings = get_settings()
    mock = settings.pathfinder_chat_provider.strip().lower() == "mock"
    if mock and cookie_token and decode_user_id(cookie_token) is not None:
        return AuthStatusResponse(signedIn=True)

    user = await current_user_on_a_site_that_answers(site_id)
    signed_in = user is not None and not user.is_guest
    if not signed_in and cookie_token is not None:
        clear_session_cookie(response)
    return AuthStatusResponse(signedIn=signed_in)
