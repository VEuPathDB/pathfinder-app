"""A turn runs under one root span, and its message names that span's trace."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from assistant_core.graph.turn_state import DurableTaskResult
from assistant_core.platform.observability import (
    install_tracer_provider,
    reset_tracer_provider,
    traced,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from pathfinder.ai.conversation._turn_helpers import build_turn_start
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.ai.conversation.turn_runner import TurnRequest, turn_trace_scope

_CONVERSATION = UUID("33333333-3333-3333-3333-333333333333")
_USER = UUID("44444444-4444-4444-4444-444444444444")
_TURN = UUID("55555555-5555-5555-5555-555555555555")


def _body() -> ChatRequestBody:
    return ChatRequestBody.model_validate(
        {
            "conversationId": str(_CONVERSATION),
            "messages": [
                {
                    "id": str(uuid4()),
                    "role": "user",
                    "parts": [{"type": "text", "text": "signal peptide genes"}],
                },
            ],
            "siteId": "plasmodb",
        },
    )


@pytest.fixture
def spans() -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    install_tracer_provider(provider, include_content=True)
    yield exporter
    reset_tracer_provider()
    provider.shutdown()


def test_the_turn_scope_names_the_assistant_the_site_and_the_models() -> None:
    request = TurnRequest(
        body=_body(),
        user_id=_USER,
        trace_labels={"tier": "default", "model_lead": "openai:gpt-lead"},
    )

    scope = turn_trace_scope(request, "pathfinder", _TURN)

    assert scope.name == "pathfinder"
    assert (scope.session_id, scope.user_id) == (_CONVERSATION, _USER)
    assert scope.tags == ("plasmodb",)
    assert scope.metadata == {
        "assistant_id": "pathfinder",
        "turn_id": str(_TURN),
        "site_id": "plasmodb",
        "turn_kind": "message",
        "tier": "default",
        "model_lead": "openai:gpt-lead",
    }
    assert scope.input_text == "signal peptide genes"


def test_a_completion_turn_is_labelled_as_one() -> None:
    result = DurableTaskResult(task_id=uuid4(), status="success", result={})
    request = TurnRequest(body=_body(), user_id=_USER, durable_result=result)

    scope = turn_trace_scope(request, "pathfinder", _TURN)

    assert scope.metadata["turn_kind"] == "durable_completion"
    assert scope.input_text == ""


def test_the_turn_start_carries_the_trace_it_runs_under(
    spans: InMemorySpanExporter,
) -> None:
    request = TurnRequest(body=_body(), user_id=_USER)
    with traced(turn_trace_scope(request, "pathfinder", _TURN)):
        start = build_turn_start(
            _body(), _USER, turn_message_id=_TURN, turn_start_event_id=0
        )

    (root,) = spans.get_finished_spans()
    assert root.context is not None
    assert start.turn_trace_id == format(root.context.trace_id, "032x")


def test_a_turn_outside_any_trace_names_none() -> None:
    start = build_turn_start(
        _body(), _USER, turn_message_id=_TURN, turn_start_event_id=0
    )

    assert (start.turn_trace_id, start.conversation_id) == (None, _CONVERSATION)
