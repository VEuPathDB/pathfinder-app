"""Test-only endpoints (available only when chat_provider=mock)."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from strategist.platform.errors import ForbiddenError
from strategist.platform.model_keys import is_mock_deployment
from strategist.platform.security import create_dev_login_token, set_dev_login_cookie
from strategist.services.audit.sample_run import SampleRunIds, store_sample_run
from strategist.services.users import get_or_create_user_id
from strategist.transport.http.deps import CurrentUser, DBSession

router = APIRouter(prefix="/api/v1/dev", tags=["dev"])


@router.post("/login")
async def dev_login(session: DBSession, user_id: str | None = None) -> JSONResponse:
    """Create a test user and return a valid auth token.

    Only available when ``STRATEGIST_CHAT_PROVIDER=mock`` in the test profile.
    The session is a synthetic user with no VEuPathDB account, so it acts as
    whatever VEuPathDB token the request carries.

    Pass ``?user_id=worker-0`` to create isolated users per Playwright
    worker so parallel tests don't share data.
    """
    if not is_mock_deployment():
        raise ForbiddenError(title="Only available in mock mode")

    external_id = f"e2e-{user_id}@test.local" if user_id else "e2e@test.local"
    internal_id = await get_or_create_user_id(session, external_id)
    auth_token = create_dev_login_token(internal_id)

    resp = JSONResponse({"authToken": auth_token, "userId": str(internal_id)})
    set_dev_login_cookie(resp, auth_token)
    return resp


@router.post("/audits/sample")
async def store_sample_audit_run(user_id: CurrentUser) -> SampleRunIds:
    if not is_mock_deployment():
        raise ForbiddenError(title="Only available in mock mode")
    return await store_sample_run(user_id)
