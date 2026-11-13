"""The CSRF header is required of cookie requests only."""

from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from strategist.platform.security import csrf_middleware

_OK = 200
_FORBIDDEN = 403


def _request(method: str, headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/api/v1/conversations",
            "query_string": b"",
            "headers": [
                (name.lower().encode(), value.encode())
                for name, value in headers.items()
            ],
        },
    )


async def _next(request: Request) -> Response:
    del request
    return PlainTextResponse("ok")


async def test_a_cookie_post_without_the_header_is_rejected() -> None:
    response = await csrf_middleware(_request("POST", {}), _next)

    assert response.status_code == _FORBIDDEN


async def test_a_cookie_post_with_the_header_passes() -> None:
    response = await csrf_middleware(
        _request("POST", {"X-Requested-With": "XMLHttpRequest"}),
        _next,
    )

    assert response.status_code == _OK


async def test_a_bearer_post_without_the_header_passes() -> None:
    response = await csrf_middleware(
        _request("POST", {"Authorization": "Bearer some.jwt.value"}),
        _next,
    )

    assert response.status_code == _OK


async def test_an_authorization_header_without_a_token_does_not_exempt() -> None:
    response = await csrf_middleware(
        _request("POST", {"Authorization": "Bearer "}), _next
    )

    assert response.status_code == _FORBIDDEN


async def test_a_non_bearer_authorization_scheme_does_not_exempt() -> None:
    response = await csrf_middleware(
        _request("POST", {"Authorization": "Basic dXNlcjpwYXNz"}),
        _next,
    )

    assert response.status_code == _FORBIDDEN


async def test_a_get_never_needs_the_header() -> None:
    response = await csrf_middleware(_request("GET", {}), _next)

    assert response.status_code == _OK
