from __future__ import annotations

from uuid import uuid4

from starlette.requests import Request

from pathfinder.platform.security import create_user_token, rate_limit_key


def _request(*, cookie: str | None = None, authorization: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = [(b"x-forwarded-for", b"203.0.113.9")]
    if cookie is not None:
        headers.append((b"cookie", f"pathfinder-auth={cookie}".encode()))
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat",
            "headers": headers,
            "client": ("10.0.0.7", 51000),
        }
    )


def test_a_signed_in_browser_is_counted_as_its_user() -> None:
    user_id = uuid4()

    key = rate_limit_key(_request(cookie=create_user_token(user_id)))

    assert key == f"user:{user_id}"


def test_a_pathfinder_bearer_is_counted_as_its_user() -> None:
    user_id = uuid4()

    key = rate_limit_key(_request(authorization=f"Bearer {create_user_token(user_id)}"))

    assert key == f"user:{user_id}"


def test_a_forged_session_is_counted_by_the_connection_address() -> None:
    assert rate_limit_key(_request(cookie="not-a-token")) == "address:10.0.0.7"


def test_no_session_is_counted_by_the_connection_address() -> None:
    assert rate_limit_key(_request()) == "address:10.0.0.7"
