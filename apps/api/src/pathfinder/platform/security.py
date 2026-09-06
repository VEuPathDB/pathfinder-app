"""Authentication, authorization, rate limiting, CSRF, and request guards."""

import json
import time
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

import jwt
from assistant_core.platform.context import (
    DEFAULT_APPLICATION_ID,
    application_id_ctx,
    user_id_ctx,
)
from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response
from fastapi.security import APIKeyCookie, APIKeyHeader, HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from jwt.types import Options
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from veupathdb.auth_context import veupathdb_auth_token_ctx

from pathfinder.platform.config import get_settings
from pathfinder.platform.error_handlers import problem_response
from pathfinder.platform.errors import ErrorCode, UnauthorizedError
from pathfinder.platform.principal import SERVICE_AUTH_HEADER, Principal
from pathfinder.services.wdk_identity import resolve_veupathdb_bearer

_JWT_ALGORITHM = "HS256"
_JWT_DECODE_OPTIONS: Options = {"require": ["exp", "sub"]}

# A request proves who it is with the browser cookie, a PathFinder bearer token,
# or a VEuPathDB bearer token; the service-token header names the caller instead.
auth_cookie = APIKeyCookie(name="pathfinder-auth", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)
service_token_header = APIKeyHeader(name=SERVICE_AUTH_HEADER, auto_error=False)

limiter = Limiter(key_func=get_remote_address)


class SessionToken(BaseModel):
    """The identity a PathFinder JWT carries.

    ``dev_login`` marks a synthetic user the dev-login route minted; it names
    no VEuPathDB account.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    user_id: UUID = Field(alias="sub")
    dev_login: bool = False


def decode_session_token(token: str) -> SessionToken | None:
    """Return the identity a PathFinder JWT carries, or None when it is not one."""
    try:
        payload = jwt.decode(
            token,
            get_settings().api_secret_key,
            algorithms=[_JWT_ALGORITHM],
            options=_JWT_DECODE_OPTIONS,
        )
        return SessionToken.model_validate(payload)
    except jwt.InvalidTokenError, ValidationError:
        return None


def decode_user_id(token: str) -> UUID | None:
    """Return the user a PathFinder JWT names, or None when it is not one."""
    claims = decode_session_token(token)
    return None if claims is None else claims.user_id


def _application_id(service_token: str | None) -> str:
    """Name the calling application. An unknown service token authenticates nobody."""
    if service_token is None:
        return DEFAULT_APPLICATION_ID
    application_id = get_settings().service_tokens.application_for(service_token)
    if application_id is None:
        raise UnauthorizedError(detail="Unknown service token")
    return application_id


async def _veupathdb_principal(token: str, application_id: str) -> Principal:
    """Identify the registered VEuPathDB user a bearer token names."""
    bearer = await resolve_veupathdb_bearer(token)
    if bearer.user_id is None:
        raise UnauthorizedError(detail=bearer.rejection)

    # WDK calls on this request act as the bearer's own user.
    veupathdb_auth_token_ctx.set(token)
    return Principal(
        user_id=bearer.user_id,
        application_id=application_id,
        credential="veupathdb-bearer",
    )


async def _identify(
    cookie_token: str | None,
    bearer: HTTPAuthorizationCredentials | None,
    application_id: str,
) -> Principal:
    """Read the request's credential: bearer first, then the cookie."""
    if bearer is not None:
        claims = decode_session_token(bearer.credentials)
        if claims is not None:
            return Principal(
                user_id=claims.user_id,
                application_id=application_id,
                credential="dev-login" if claims.dev_login else "pathfinder-bearer",
            )
        return await _veupathdb_principal(bearer.credentials, application_id)

    if cookie_token:
        claims = decode_session_token(cookie_token)
        if claims is not None:
            return Principal(
                user_id=claims.user_id,
                application_id=application_id,
                credential="dev-login" if claims.dev_login else "pathfinder-cookie",
            )

    raise UnauthorizedError(detail="Not authenticated")


async def resolve_principal(
    cookie_token: Annotated[str | None, Depends(auth_cookie)] = None,
    bearer: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ] = None,
    service_token: Annotated[str | None, Depends(service_token_header)] = None,
) -> Principal:
    """Identify the request, or raise UnauthorizedError."""
    principal = await _identify(
        cookie_token,
        bearer,
        _application_id(service_token),
    )
    user_id_ctx.set(principal.user_id)
    application_id_ctx.set(principal.application_id)
    return principal


async def get_current_user(
    principal: Annotated[Principal, Depends(resolve_principal)],
) -> UUID:
    """Return the current user ID."""
    return principal.user_id


def _encode(claims: SessionToken, expires_in: int) -> str:
    payload = claims.model_dump(by_alias=True, mode="json")
    payload["exp"] = int(time.time()) + expires_in
    return jwt.encode(
        payload,
        get_settings().api_secret_key,
        algorithm=_JWT_ALGORITHM,
    )


def create_user_token(user_id: UUID, expires_in: int = 86400) -> str:
    """Create a signed JWT for a user.

    :param expires_in: Token lifetime in seconds.
    """
    return _encode(SessionToken(sub=user_id), expires_in)


def create_dev_login_token(user_id: UUID, expires_in: int = 86400) -> str:
    """Create a signed JWT for a synthetic user with no VEuPathDB account.

    The dev-login route is the only caller; it mounts under the mock overlay.
    """
    return _encode(SessionToken(sub=user_id, dev_login=True), expires_in)


_CSRF_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _carries_bearer_credentials(request: Request) -> bool:
    scheme, _, credentials = request.headers.get("Authorization", "").partition(" ")
    return scheme.lower() == "bearer" and bool(credentials.strip())


async def csrf_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Require the X-Requested-With header on state-changing cookie requests.

    A browser sets neither that header cross-origin nor an Authorization
    header, so a forged request can carry neither.
    """
    if (
        request.method not in _CSRF_SAFE_METHODS
        and not _carries_bearer_credentials(request)
        and not request.headers.get("X-Requested-With", "").strip()
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": "Missing required X-Requested-With header"},
        )
    return await call_next(request)


class RejectNullBytesMiddleware:
    """Reject a NUL character in the URL or a JSON body before the route runs.

    PostgreSQL text cannot hold NUL. The check must precede the route, because
    a body value reaches the database at commit time, after the response, where
    exception handlers no longer apply. Pure ASGI, so the body can be read and
    replayed to the app.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if "\x00" in request.url.path or any(
            "\x00" in key or "\x00" in value
            for key, value in request.query_params.multi_items()
        ):
            await self._reject(request, "URL", scope, receive, send)
            return

        if not _is_json_request(request):
            await self.app(scope, receive, send)
            return

        body, messages = await _drain_body(receive)
        if _body_carries_null(body):
            await self._reject(request, "Request body", scope, receive, send)
            return

        await self.app(scope, _replay(messages, receive), send)

    async def _reject(
        self,
        request: Request,
        source: str,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        response = problem_response(
            request,
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code=ErrorCode.VALIDATION_ERROR,
            title="Request validation failed",
            detail=f"{source} must not contain null characters",
        )
        await response(scope, receive, send)


def _is_json_request(request: Request) -> bool:
    return "json" in request.headers.get("content-type", "")


def _body_carries_null(body: bytes) -> bool:
    """Report whether a JSON body decodes to a string that contains NUL.

    A NUL arrives as an escape sequence, and those same bytes can also spell an
    escaped backslash, so the byte scan is only a prefilter. The parsed value
    decides.
    """
    if b"\x00" not in body and b"\\u0000" not in body:
        return False
    try:
        parsed = json.loads(body)
    except ValueError:
        # The route owns the error for malformed JSON.
        return False
    return _contains_null(parsed)


def _contains_null(value: object) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(
            _contains_null(key) or _contains_null(item) for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_null(item) for item in value)
    return False


async def _drain_body(receive: Receive) -> tuple[bytes, list[Message]]:
    """Read the request body to completion, and keep every message for replay."""
    body = bytearray()
    messages: list[Message] = []
    more_body = True
    while more_body:
        message = await receive()
        messages.append(message)
        if message["type"] != "http.request":
            break
        body.extend(message.get("body", b""))
        more_body = bool(message.get("more_body", False))
    return bytes(body), messages


def _replay(messages: list[Message], receive: Receive) -> Receive:
    """Return a receive callable that replays drained messages, then the real stream."""
    pending = iter(messages)

    async def replayed() -> Message:
        return next(pending, None) or await receive()

    return replayed
