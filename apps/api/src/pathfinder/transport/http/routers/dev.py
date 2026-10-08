"""Test-only endpoints (available only when chat_provider=mock)."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import ForbiddenError
from pathfinder.platform.security import create_dev_login_token, set_session_cookie
from pathfinder.services.users import get_or_create_user_id
from pathfinder.transport.http.deps import DBSession

router = APIRouter(prefix="/api/v1/dev", tags=["dev"])


def _is_mock_provider() -> bool:
    return get_settings().pathfinder_chat_provider.strip().lower() == "mock"


@router.post("/login")
async def dev_login(session: DBSession, user_id: str | None = None) -> JSONResponse:
    """Create a test user and return a valid auth token.

    Only available when ``PATHFINDER_CHAT_PROVIDER=mock`` in the test profile.
    The session is a synthetic user with no VEuPathDB account, so it acts as
    whatever VEuPathDB token the request carries.

    Pass ``?user_id=worker-0`` to create isolated users per Playwright
    worker so parallel tests don't share data.
    """
    if not _is_mock_provider():
        raise ForbiddenError(title="Only available in mock mode")

    external_id = f"e2e-{user_id}@test.local" if user_id else "e2e@test.local"
    internal_id = await get_or_create_user_id(session, external_id)
    auth_token = create_dev_login_token(internal_id)

    resp = JSONResponse({"authToken": auth_token, "userId": str(internal_id)})
    set_session_cookie(resp, auth_token)
    return resp
