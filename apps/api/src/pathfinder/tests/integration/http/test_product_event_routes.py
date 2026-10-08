"""Reporting a product event over HTTP: what is recorded, what is refused, and its span."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.main import create_app
from pathfinder.platform.config import get_settings
from pathfinder.platform.langfuse.events import ProductEvent
from pathfinder.platform.security import site_login_user
from pathfinder.tests.integration.http.conftest import client_for, make_user
from pathfinder.transport.http.routers import product_events

_URL = "/api/v1/product-events"
_NO_CONTENT = 204
_UNPROCESSABLE = 422


@pytest.fixture
async def user_id(db_session: AsyncSession, patch_app_db_engine: None) -> UUID:
    del patch_app_db_engine
    return (await make_user(db_session)).id


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[ProductEvent]:
    events: list[ProductEvent] = []
    monkeypatch.setattr(product_events, "record_product_event", events.append)
    return events


@pytest.fixture
async def client(
    app: FastAPI, user_id: UUID, site_login_matches_session: None
) -> AsyncGenerator[httpx.AsyncClient]:
    del site_login_matches_session
    async with client_for(app, user_id) as client:
        yield client


async def test_an_answered_card_is_recorded_on_its_thread(
    client: httpx.AsyncClient, user_id: UUID, recorded: list[ProductEvent]
) -> None:
    conversation_id = uuid4()

    response = await client.post(
        _URL,
        json={
            "event": "card_answered",
            "conversationId": str(conversation_id),
            "toolName": "propose_changes",
            "approved": True,
        },
    )

    assert response.status_code == _NO_CONTENT
    assert recorded == [
        ProductEvent(
            name="card_answered",
            user_id=user_id,
            conversation_id=conversation_id,
            attributes={"tool_name": "propose_changes", "approved": True},
        ),
    ]


async def test_an_unset_field_is_left_out_of_the_event(
    client: httpx.AsyncClient, recorded: list[ProductEvent]
) -> None:
    response = await client.post(
        _URL, json={"event": "strategy_opened", "siteId": "plasmodb"}
    )

    assert response.status_code == _NO_CONTENT
    assert [(e.name, e.conversation_id, e.attributes) for e in recorded] == [
        ("strategy_opened", None, {"site_id": "plasmodb"}),
    ]


@pytest.mark.parametrize(
    "body",
    [
        {"event": "card_answered", "toolName": "propose_changes"},
        {"event": "message_rated", "messageId": "m1"},
        {"event": "site_switched", "fromSite": "plasmodb", "toSite": 7},
    ],
)
async def test_a_malformed_event_is_422_and_records_nothing(
    client: httpx.AsyncClient, recorded: list[ProductEvent], body: dict[str, object]
) -> None:
    response = await client.post(_URL, json=body)

    assert response.status_code == _UNPROCESSABLE
    assert recorded == []


@pytest.fixture
def request_spans(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    yield exporter
    provider.shutdown()


async def test_a_request_is_one_server_span_with_its_user_and_request_id(
    request_spans: InMemorySpanExporter,
    user_id: UUID,
    recorded: list[ProductEvent],
) -> None:
    del recorded
    get_settings.cache_clear()
    traced_app = create_app()

    async def _site_user() -> UUID:
        return user_id

    traced_app.dependency_overrides[site_login_user] = _site_user

    async with client_for(traced_app, user_id) as client:
        response = await client.post(
            _URL,
            json={"event": "export_requested", "exportKind": "gene_list"},
            headers={"X-Request-ID": "req-product-event"},
        )

    assert response.status_code == _NO_CONTENT
    servers = [
        span
        for span in request_spans.get_finished_spans()
        if span.kind == trace.SpanKind.SERVER
    ]
    assert [span.name for span in servers] == [f"POST {_URL}"]
    attributes = dict(servers[0].attributes or {})
    assert attributes["user.id"] == str(user_id)
    assert attributes["app.request_id"] == "req-product-event"
