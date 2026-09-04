"""Shared fixtures and request builders for the HTTP integration tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterable, Iterator
from typing import Any, Literal
from uuid import UUID, uuid4

import httpx
import pytest
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pathfinder.persistence.models import User
from pathfinder.platform.config import get_settings
from pathfinder.platform.principal import SERVICE_AUTH_HEADER
from pathfinder.platform.security import create_user_token

CHAT_TURN_TASK = "chat_turn:run"
WDK_AUTH_HEADER = "X-VEUPATHDB-AUTH"
_EVENT_STREAM = b"text/event-stream"

OTHER_APPLICATION_ID = "companion"
OTHER_APPLICATION_SECRET = "companion-application-service-secret-01"


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


async def make_user(session: AsyncSession) -> User:
    user = User(id=uuid4())
    session.add(user)
    await session.flush()
    await session.commit()
    return user


def client_for(
    app: ASGIApp, user_id: UUID, wdk_token: str | None = None
) -> httpx.AsyncClient:
    """A client that acts as ``user_id``; ``wdk_token`` names the WDK account."""
    headers = {"X-Requested-With": "XMLHttpRequest"}
    if wdk_token is not None:
        # The header the request resolver reads into veupathdb_auth_token_ctx.
        headers[WDK_AUTH_HEADER] = wdk_token
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers=headers,
        cookies={"pathfinder-auth": create_user_token(user_id)},
    )


@pytest.fixture
def other_application(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Register a second calling application and return its id."""
    monkeypatch.setenv(
        "PATHFINDER_SERVICE_TOKENS",
        f"{OTHER_APPLICATION_ID}:{OTHER_APPLICATION_SECRET}",
    )
    get_settings.cache_clear()
    yield OTHER_APPLICATION_ID
    get_settings.cache_clear()


def other_application_client_for(app: ASGIApp, user_id: UUID) -> httpx.AsyncClient:
    """The same user, calling from the application the service token names."""
    client = client_for(app, user_id)
    client.headers[SERVICE_AUTH_HEADER] = OTHER_APPLICATION_SECRET
    return client


def _is_event_stream(headers: Iterable[tuple[bytes, bytes]]) -> bool:
    return any(
        key.lower() == b"content-type" and value.startswith(_EVENT_STREAM)
        for key, value in headers
    )


def ends_at_first_frame(app: ASGIApp) -> ASGIApp:
    """Close a ``text/event-stream`` response as soon as it sets its status.

    ``httpx.ASGITransport`` runs the app to completion first, so a caller that
    needs only the status would wait for the whole stream. Other responses pass.
    """

    async def wrapped(scope: Scope, receive: Receive, send: Send) -> None:
        closed = asyncio.Event()

        async def capture(message: Message) -> None:
            if closed.is_set():
                return
            await send(message)
            if message["type"] == "http.response.start" and _is_event_stream(
                message.get("headers", ()),
            ):
                await send({"type": "http.response.body", "body": b""})
                closed.set()

        call = asyncio.create_task(app(scope, receive, capture))
        waiter = asyncio.create_task(closed.wait())
        done, _pending = await asyncio.wait(
            {call, waiter},
            return_when=asyncio.FIRST_COMPLETED,
        )
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        if call in done:
            call.result()
            return
        call.cancel()
        await asyncio.gather(call, return_exceptions=True)

    return wrapped


def first_frame_client_for(
    app: ASGIApp, user_id: UUID, wdk_token: str | None = None
) -> httpx.AsyncClient:
    """Like :func:`client_for`, but a streamed response ends at its status line."""
    return client_for(ends_at_first_frame(app), user_id, wdk_token)


def chat_body(
    conversation_id: UUID,
    *,
    message_id: str | None = None,
    trigger: Literal["submit-message", "regenerate-message"] = "submit-message",
) -> dict[str, Any]:
    resolved_id = message_id if message_id is not None else str(uuid4())
    return {
        "trigger": trigger,
        "id": resolved_id,
        "messages": [
            {
                "id": resolved_id,
                "role": "user",
                "parts": [{"type": "text", "text": "list the kinases"}],
            },
        ],
        "conversationId": str(conversation_id),
        "siteId": "plasmodb",
    }


def chat_jobs(connector: InMemoryConnector) -> list[dict[str, Any]]:
    return [j for j in connector.jobs.values() if j["task_name"] == CHAT_TURN_TASK]
