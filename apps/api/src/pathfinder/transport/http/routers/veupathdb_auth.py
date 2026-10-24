"""Whether the request carries a registered VEuPathDB login."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from pathfinder.platform.model_keys import is_mock_deployment
from pathfinder.platform.security import decode_session_token, dev_login_cookie
from pathfinder.services.wdk_identity import (
    current_user_on_a_site_that_answers,
)
from pathfinder.transport.http.schemas import (
    AuthStatusResponse,
)
from pathfinder.transport.http.schemas.site_id import SiteId

router = APIRouter(prefix="/api/v1/veupathdb/auth", tags=["veupathdb-auth"])


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(
    dev_login: Annotated[str | None, Depends(dev_login_cookie)] = None,
    site_id: Annotated[SiteId, Query(alias="siteId")] = "veupathdb",
) -> AuthStatusResponse:
    """Return the current VEuPathDB auth status.

    A refused token or a guest is signed out; a site that does not answer is a
    503. A mock chat provider has no VEuPathDB session, so its dev-login cookie
    alone proves identity there.
    """
    mock = is_mock_deployment()
    claims = decode_session_token(dev_login) if dev_login else None
    if mock and claims is not None and claims.dev_login:
        return AuthStatusResponse(signedIn=True)

    user = await current_user_on_a_site_that_answers(site_id)
    return AuthStatusResponse(signedIn=user is not None and not user.is_guest)
