"""Local development sign-in that sets the cookie a VEuPathDB website sets."""

import httpx
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from veupathdb.wdk import password_login

from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import (
    SiteUnavailableError,
    UnauthorizedError,
    site_failure_reason,
)

router = APIRouter(prefix="/api/v1/dev", tags=["dev"], include_in_schema=False)


@router.get("/site-login")
async def site_login(destination: str = "") -> RedirectResponse:
    settings = get_settings()
    base = settings.public_base_url
    try:
        token = await password_login(
            settings.pathfinder_site,
            settings.wdk_dev_email,
            settings.wdk_dev_password.get_secret_value(),
            redirect_url=base,
        )
    except httpx.HTTPError as e:
        raise SiteUnavailableError(
            settings.pathfinder_site, site_failure_reason(e)
        ) from e
    if not token:
        raise UnauthorizedError(detail="The development account did not sign in")
    target = destination if destination.startswith(f"{base}/") else base
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(key="Authorization", value=token, samesite="lax", path="/")
    return response
