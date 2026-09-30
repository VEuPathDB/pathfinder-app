"""A product event lands on its conversation's session, attributed to its user."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from pathfinder.platform.langfuse import events
from pathfinder.platform.langfuse.events import ProductEvent, record_product_event

_USER = UUID("66666666-6666-6666-6666-666666666666")
_CONVERSATION = UUID("77777777-7777-7777-7777-777777777777")


@dataclass(frozen=True)
class _Sdk:
    client: Langfuse
    exporter: InMemorySpanExporter

    def exported(self) -> dict[str, object]:
        self.client.flush()
        (span,) = self.exporter.get_finished_spans()
        return {"name": span.name, **dict(span.attributes or {})}


@pytest.fixture
def sdk(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Sdk]:
    exporter = InMemorySpanExporter()
    client = Langfuse(
        # The SDK keeps one resource manager per public key.
        public_key=f"pk-lf-{uuid4()}",
        secret_key="sk-lf-test",
        host="http://langfuse.invalid",
        tracer_provider=TracerProvider(),
        span_exporter=exporter,
    )
    monkeypatch.setattr(events, "get_langfuse", lambda: client)
    yield _Sdk(client=client, exporter=exporter)
    client.shutdown()


def test_an_event_is_one_root_observation_on_the_session(sdk: _Sdk) -> None:
    record_product_event(
        ProductEvent(
            name="card_answered",
            user_id=_USER,
            conversation_id=_CONVERSATION,
            attributes={"tool": "propose_changes", "approved": "true"},
        ),
    )

    exported = sdk.exported()

    assert exported["name"] == "product.card_answered"
    assert exported["session.id"] == str(_CONVERSATION)
    assert exported["user.id"] == str(_USER)
    assert exported["langfuse.trace.name"] == "product.card_answered"
    assert exported["langfuse.trace.tags"] == ("product-event",)
    assert exported["langfuse.observation.type"] == "event"
    assert exported["langfuse.observation.metadata.tool"] == "propose_changes"
    assert exported["langfuse.observation.metadata.approved"] == "true"


def test_an_event_sent_inside_a_request_span_is_a_root_of_its_own(
    sdk: _Sdk,
) -> None:
    request_tracer = TracerProvider().get_tracer("request")

    with request_tracer.start_as_current_span("POST /api/v1/product-events") as outer:
        record_product_event(ProductEvent(name="turn_undone", user_id=_USER))
    sdk.client.flush()
    (event,) = sdk.exporter.get_finished_spans()

    assert event.parent is None
    assert event.context is not None
    assert event.context.trace_id != outer.get_span_context().trace_id


def test_an_event_without_a_thread_names_only_its_user(sdk: _Sdk) -> None:
    record_product_event(
        ProductEvent(
            name="site_switched",
            user_id=_USER,
            attributes={"from_site": "plasmodb", "to_site": "toxodb"},
        ),
    )

    exported = sdk.exported()

    assert exported["user.id"] == str(_USER)
    assert "session.id" not in exported


def test_without_langfuse_an_event_is_dropped(
    sdk: _Sdk, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(events, "get_langfuse", lambda: None)

    record_product_event(ProductEvent(name="export_requested", user_id=_USER))

    sdk.client.flush()
    assert sdk.exporter.get_finished_spans() == ()
