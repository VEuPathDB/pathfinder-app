from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.conversation.event_tail import event_tail


def test_no_cache_or_proxy_holds_the_tail() -> None:
    response = event_tail(uuid4(), after=0)

    assert response.headers["cache-control"] == "no-cache, no-transform"


def test_the_tail_is_a_ui_message_event_stream() -> None:
    response = event_tail(uuid4(), after=0)

    assert (
        response.headers["content-type"],
        response.headers["x-vercel-ai-ui-message-stream"],
    ) == ("text/event-stream; charset=utf-8", "v1")
