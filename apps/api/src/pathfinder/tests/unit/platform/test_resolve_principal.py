"""The credential order, and the request-scoped identity the resolver publishes."""

import time
from collections.abc import Iterator
from uuid import uuid4

import jwt
import pytest
from assistant_core.platform.context import application_id_ctx, user_id_ctx
from fastapi.security.http import HTTPAuthorizationCredentials

from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import UnauthorizedError
from pathfinder.platform.security import (
    create_dev_login_token,
    create_user_token,
    decode_user_id,
    resolve_principal,
)

SERVICE_SECRET = "analytics-service-secret-0123456789"


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture
def service_tokens(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PATHFINDER_SERVICE_TOKENS", f"analytics:{SERVICE_SECRET}")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_a_cookie_names_the_user_and_the_default_application() -> None:
    user_id = uuid4()

    principal = await resolve_principal(
        cookie_token=create_user_token(user_id), site_user=user_id
    )

    assert principal.user_id == user_id
    assert principal.credential == "pathfinder-cookie"
    assert principal.application_id == "pathfinder"


async def test_a_pathfinder_bearer_wins_over_the_cookie() -> None:
    cookie_user = uuid4()
    bearer_user = uuid4()

    principal = await resolve_principal(
        cookie_token=create_user_token(cookie_user),
        bearer=_bearer(create_user_token(bearer_user)),
    )

    assert principal.user_id == bearer_user
    assert principal.credential == "pathfinder-bearer"


async def test_a_dev_login_cookie_names_the_dev_login_credential() -> None:
    user_id = uuid4()

    principal = await resolve_principal(cookie_token=create_dev_login_token(user_id))

    assert principal.user_id == user_id
    assert principal.credential == "dev-login"


async def test_a_dev_login_bearer_names_the_dev_login_credential() -> None:
    user_id = uuid4()

    principal = await resolve_principal(bearer=_bearer(create_dev_login_token(user_id)))

    assert principal.user_id == user_id
    assert principal.credential == "dev-login"


async def test_no_credential_is_unauthorized() -> None:
    with pytest.raises(UnauthorizedError, match="Not authenticated"):
        await resolve_principal()


async def test_an_expired_cookie_is_unauthorized() -> None:
    with pytest.raises(UnauthorizedError):
        await resolve_principal(cookie_token=create_user_token(uuid4(), expires_in=-60))


async def test_a_token_whose_subject_is_not_a_string_names_no_user() -> None:
    signed = jwt.encode(
        {"sub": 12345, "exp": int(time.time()) + 600},
        get_settings().api_secret_key,
        algorithm="HS256",
    )

    assert decode_user_id(signed) is None

    with pytest.raises(UnauthorizedError):
        await resolve_principal(cookie_token=signed)


async def test_the_resolver_publishes_the_identity_to_the_request_context(
    service_tokens: None,
) -> None:
    del service_tokens
    user_id = uuid4()

    await resolve_principal(
        cookie_token=create_user_token(user_id),
        service_token=SERVICE_SECRET,
        site_user=user_id,
    )

    assert user_id_ctx.get() == user_id
    assert application_id_ctx.get() == "analytics"


async def test_an_unknown_service_token_is_unauthorized(service_tokens: None) -> None:
    del service_tokens

    with pytest.raises(UnauthorizedError, match="Unknown service token"):
        await resolve_principal(
            cookie_token=create_user_token(uuid4()),
            service_token="not-the-configured-secret-0123456789",
        )
