"""A researcher's key reaches the provider and no other place.

Every sink a turn writes is read back for the key: the chunk log, the graph
checkpoints, the job payload, the message metadata, the process log, and the
spans the tracing exporter and the Langfuse filter receive.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator, Sequence
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.conversation.event_writer import ChatEventWriter
from assistant_core.conversation.vercel_adapter import PhaseStreamEmitter
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from procrastinate.testing import InMemoryConnector
from pydantic import SecretStr
from pydantic_ai import Agent
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.models.instrumented import InstrumentationSettings
from sqlalchemy import select, table, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.domain.provider_keys import ProviderKeyring
from pathfinder.jobs import turn_keys
from pathfinder.jobs.auth_context import attach_application
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.langfuse.client import _should_export_span
from pathfinder.platform.model_keys import attach_keyring, keyed_model
from pathfinder.platform.security import create_user_token
from pathfinder.services.provider_keys import load_keyring, store_key
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests._support.provider_wire import (
    ANSWER_TEXT,
    ProviderWire,
    allow_requests_to_the_wire,
)
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import make_user

_SENTINEL = "sk-proj-sentinel-4f1d9c2e7a0b5WXYZ"
_REFUSAL_FRAGMENTS = ("sk-proj-", "Incorrect API key")
_TABLES = (
    "conversation_events",
    "messages",
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
)
_DEADLOCK_CEILING_SECONDS = 120.0


@pytest.fixture
def _sealed(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with sealed_provider_keys(monkeypatch):
        yield


def _as_text(value: object) -> str:
    """A column as text. Checkpoint bytes keep a string they carry readable."""
    match value:
        case bytes():
            return value.decode("utf-8", errors="replace")
        case _:
            return str(value)


async def _stored_text(session: AsyncSession) -> str:
    """Every row of every table a turn writes, as one text."""
    rows: list[str] = []
    for name in _TABLES:
        exists = await session.scalar(
            text("SELECT to_regclass(:name)").bindparams(name=f"public.{name}")
        )
        if exists is None:
            continue
        result = await session.execute(select(text("*")).select_from(table(name)))
        rows.extend(" ".join(_as_text(value) for value in row) for row in result.all())
    return "\n".join(rows)


def _logged(records: Sequence[logging.LogRecord]) -> str:
    return "\n".join(f"{record.msg} {record.getMessage()}" for record in records)


def _span_text(spans: Sequence[ReadableSpan]) -> str:
    parts: list[str] = []
    for span in spans:
        parts.append(str(dict(span.attributes or {})))
        parts.extend(str(dict(event.attributes or {})) for event in span.events)
        parts.append(str(span.status.description))
    return "\n".join(parts)


@pytest.fixture
def opened_keyrings(monkeypatch: pytest.MonkeyPatch) -> list[ProviderKeyring]:
    """Every keyring the worker opens, kept for the test to read."""
    opened: list[ProviderKeyring] = []

    async def load_and_keep(user_id: UUID) -> ProviderKeyring:
        keyring = await load_keyring(user_id)
        opened.append(keyring)
        return keyring

    monkeypatch.setattr(turn_keys, "load_keyring", load_and_keep)
    return opened


@pytest.mark.usefixtures("_sealed", "signed_in_to_veupathdb", "patch_app_db_engine")
async def test_a_turn_under_a_key_writes_the_key_nowhere(
    app: FastAPI,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    in_memory_jobs: InMemoryConnector,
    caplog: pytest.LogCaptureFixture,
    opened_keyrings: list[ProviderKeyring],
) -> None:
    """The worker opens the key the researcher stored, and no sink holds it."""
    async with attach_application(), session_maker() as session:
        await store_key(session, authed_user_id, "openai", SecretStr(_SENTINEL))
        await session.commit()

    with caplog.at_level(logging.DEBUG):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={"pathfinder-auth": create_user_token(authed_user_id)},
            headers={"X-Requested-With": "XMLHttpRequest"},
        ) as client:
            post = asyncio.create_task(
                client.post(
                    "/api/v1/chat",
                    json=chat_post_body(uuid4(), "list the kinases"),
                    timeout=_DEADLOCK_CEILING_SECONDS,
                ),
            )
            await asyncio.wait_for(
                wait_until_chat_turn_deferred(in_memory_jobs),
                timeout=_DEADLOCK_CEILING_SECONDS,
            )
            jobs = str(list(in_memory_jobs.jobs.values()))
            await run_deferred_chat_turns()
            response = await asyncio.wait_for(post, timeout=_DEADLOCK_CEILING_SECONDS)

    assert "finish" in [c["type"] for c in parse_sse_body(response.text)]
    assert [
        {name: key.get_secret_value() for name, key in ring.active.items()}
        for ring in opened_keyrings
    ] == [{"openai": _SENTINEL}]
    async with session_maker() as session:
        stored = await _stored_text(session)
    assert "list the kinases" in stored
    assert _SENTINEL not in stored
    assert _SENTINEL not in jobs
    assert _SENTINEL not in _logged(caplog.records)
    assert _SENTINEL not in response.text


async def _keyed_run(
    wire: ProviderWire,
    session_maker: async_sessionmaker[AsyncSession],
) -> tuple[str, list[ReadableSpan]]:
    """One keyed agent run streamed into the chunk log, and the spans it made."""
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    async with session_maker() as session:
        user = await make_user(session)
        conversation = Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID,
            user_id=user.id,
            site_id="plasmodb",
            name="kinases",
        )
        session.add(conversation)
        await session.commit()
    writer = ChatEventWriter(conversation_id=conversation.id, turn_id=uuid4())
    keyring = ProviderKeyring(active={"openai": SecretStr(_SENTINEL)})
    with attach_keyring(keyring, build=wire.build):
        settings = InstrumentationSettings(
            tracer_provider=tracer_provider, include_content=True
        )
        agent = Agent(
            keyed_model("openai:gpt-5.6-luna"),
            capabilities=[Instrumentation(settings=settings)],
        )
        emitter = PhaseStreamEmitter(message_id=str(uuid4()))
        async with agent.run_stream_events("list the kinases") as events:
            async for chunk in emitter.chunks(events):
                await writer.write(
                    chunk.model_dump(by_alias=True, mode="json", exclude_none=True)
                )
    async with session_maker() as session:
        stored = await _stored_text(session)
    return stored, list(exporter.get_finished_spans())


@pytest.fixture
def _keyed_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    allow_requests_to_the_wire(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "default")
    monkeypatch.setattr(settings, "otel_include_content", True)


@pytest.mark.usefixtures("_keyed_cloud")
async def test_an_answered_keyed_run_leaves_the_key_in_no_row_and_no_span(
    patch_app_db_engine: None,
    db_cleaner: None,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    del patch_app_db_engine, db_cleaner
    wire = ProviderWire()

    stored, spans = await _keyed_run(wire, session_maker)

    assert [h["authorization"] for h in wire.sent_headers()] == [f"Bearer {_SENTINEL}"]
    assert ANSWER_TEXT in stored
    assert spans != []
    assert _SENTINEL not in stored
    assert _SENTINEL not in _span_text(spans)
    assert _SENTINEL not in _span_text([s for s in spans if _should_export_span(s)])


@pytest.mark.usefixtures("_keyed_cloud")
async def test_a_refused_keyed_run_leaves_no_fragment_of_the_refusal_anywhere(
    patch_app_db_engine: None,
    db_cleaner: None,
    session_maker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    del patch_app_db_engine, db_cleaner
    wire = ProviderWire(refuse=True)

    with caplog.at_level(logging.DEBUG):
        stored, spans = await _keyed_run(wire, session_maker)

    assert len(wire.requests) == 1
    assert "OpenAI refused the key you added" in stored
    everywhere = "\n".join(
        [stored, _span_text(spans), _logged(caplog.records)],
    )
    assert [f for f in (_SENTINEL, *_REFUSAL_FRAGMENTS) if f in everywhere] == []
