"""The largest request body the api reads, enforced before any route or middleware reads one."""

from __future__ import annotations

from http import HTTPStatus

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pathfinder.platform.error_handlers import problem_response
from pathfinder.platform.errors import ErrorCode


class _BodyTooLargeError(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Answer 413 for a body over ``max_bytes``, declared or streamed."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = Request(scope).headers.get("content-length", "")
        if declared.isdigit() and int(declared) > self.max_bytes:
            await self._refuse(scope, receive, send)
            return

        received = 0
        started = False

        async def counted() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLargeError
            return message

        async def tracked(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted, tracked)
        except _BodyTooLargeError:
            if started:
                raise
            await self._refuse(scope, receive, send)

    async def _refuse(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = problem_response(
            Request(scope),
            status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            code=ErrorCode.VALIDATION_ERROR,
            title="Request body too large",
            detail=f"The request body is larger than {self.max_bytes} bytes.",
        )
        await response(scope, receive, send)
