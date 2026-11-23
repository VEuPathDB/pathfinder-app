from uuid import UUID

from fastapi.responses import Response

from strategist.platform.config import BASE_PATH, get_settings
from strategist.platform.security import (
    DEV_LOGIN_COOKIE,
    SessionToken,
    encode_session_token,
)


def create_dev_login_token(user_id: UUID, expires_in: int = 86400) -> str:
    return encode_session_token(SessionToken(sub=user_id, dev_login=True), expires_in)


def set_dev_login_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=DEV_LOGIN_COOKIE,
        value=token,
        path=BASE_PATH,
        httponly=True,
        samesite="lax",
        secure=not get_settings().is_development,
    )
