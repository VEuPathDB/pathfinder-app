"""A chat turn run by the worker is one trace, and its message names that trace."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Message
from assistant_core.platform.observability import (
    install_tracer_provider,
    reset_tracer_provider,
)
from fastapi import FastAPI
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from procrastinate.testing import InMemoryConnector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.tests.integration.chat._helpers import run_one_chat_turn

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb"
)

_PROMPT = "Which genes have a signal peptide?"


@pytest.fixture
def spans() -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    install_tracer_provider(provider, include_content=True)
    yield exporter
    reset_tracer_provider()
    provider.shutdown()


def _turn_root(finished: tuple[ReadableSpan, ...]) -> ReadableSpan:
    roots = [s for s in finished if s.parent is None and s.name == "pathfinder"]
    assert len(roots) == 1
    return roots[0]


def _trace_of(span: ReadableSpan) -> int:
    assert span.context is not None
    trace_id: int = span.context.trace_id
    return trace_id


async def test_a_turn_is_one_root_span_on_its_session_with_its_models(
    app: FastAPI,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    session_maker: async_sessionmaker[AsyncSession],
    spans: InMemorySpanExporter,
) -> None:
    conversation_id = uuid4()

    await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=_PROMPT,
        conversation_id=conversation_id,
    )

    finished = spans.get_finished_spans()
    root = _turn_root(finished)
    attributes = dict(root.attributes or {})
    assert attributes["session.id"] == str(conversation_id)
    assert attributes["user.id"] == str(authed_user_id)
    assert attributes["langfuse.trace.tags"] == ("plasmodb",)
    assert attributes["langfuse.trace.input"] == _PROMPT
    metadata = {
        key.removeprefix("langfuse.trace.metadata."): value
        for key, value in attributes.items()
        if key.startswith("langfuse.trace.metadata.")
    }
    assert {
        "assistant_id",
        "turn_id",
        "site_id",
        "turn_kind",
        "provider",
        "tier",
        "model_lead",
    } <= metadata.keys()
    assert (metadata["assistant_id"], metadata["site_id"], metadata["turn_kind"]) == (
        "pathfinder",
        "plasmodb",
        "message",
    )

    in_turn = [s for s in finished if _trace_of(s) == _trace_of(root)]
    model_calls = [s for s in in_turn if "gen_ai.request.model" in (s.attributes or {})]
    assert {s.name.split(" ")[0] for s in model_calls} == {"chat"}
    assert {(s.attributes or {}).get("session.id") for s in model_calls} == {
        str(conversation_id)
    }

    async with session_maker() as session:
        metadata_rows = (
            await session.scalars(
                select(Message.metadata_).where(
                    Message.conversation_id == conversation_id,
                    Message.role == "assistant",
                ),
            )
        ).all()
    assert [row["traceId"] for row in metadata_rows] == [
        format(_trace_of(root), "032x")
    ]
