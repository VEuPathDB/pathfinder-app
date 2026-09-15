"""What a turn that failed tells the user, and what it keeps out of the thread.

The reply names the shape of the failure. A provider's response body, a header
and a url with a query are the provider's, not the reader's, and the reply is
persisted and read back on the next turn.
"""

from __future__ import annotations

from pydantic_ai.exceptions import ModelHTTPError

from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_stops import (
    MAX_FAILURE_CLAUSE_CHARS,
    fallback_prose,
    final_reply,
)
from pathfinder.ai.lead.turn_contract import LeadResponse

_ORG = "org-abc123"
_RATE_LIMIT = ModelHTTPError(
    status_code=429,
    model_name="gpt-5.6-luna",
    body={
        "error": {
            "message": f"Rate limit reached for {_ORG} on tokens",
            "type": "tokens",
            "docs": "https://platform.example/limits?org=abc123",
        },
    },
)


def _failed(error: str) -> _LeadRunCapture:
    capture = _LeadRunCapture()
    capture.run_error = error
    return capture


def test_a_provider_error_names_its_status_and_not_its_body() -> None:
    prose = fallback_prose(_failed(str(_RATE_LIMIT)))

    assert prose == (
        "I stopped this turn on an error I could not recover from: the model "
        "provider answered 429. Send the message again and I will start over "
        "from it."
    )
    assert _ORG not in prose
    assert "body" not in prose


def test_a_transport_failure_still_names_what_happened() -> None:
    prose = fallback_prose(_failed("peer closed connection"))

    assert prose == (
        "I stopped this turn on an error I could not recover from: peer closed "
        "connection. Send the message again and I will start over from it."
    )


def test_a_url_with_a_query_is_not_read_back_to_the_user() -> None:
    prose = fallback_prose(
        _failed("request to https://api.example/v1/chat?key=sk-live-9f2 failed"),
    )

    assert "https://" not in prose
    assert "sk-live-9f2" not in prose
    assert "request to failed" in prose


def test_a_failure_that_is_only_a_payload_still_says_the_run_failed() -> None:
    prose = fallback_prose(_failed('{"error": {"message": "nope"}}'))

    assert "nope" not in prose
    assert "the run failed" in prose


def test_a_long_failure_is_cut_to_one_clause() -> None:
    words = " ".join(["overload"] * 60)
    prose = fallback_prose(_failed(f"{words}\nsecond line"))

    assert "second line" not in prose
    assert len(prose) < len(words)
    assert prose.count("overload") <= MAX_FAILURE_CLAUSE_CHARS // len("overload ") + 1


def test_a_run_that_ended_without_a_reply_and_without_an_error_asks_for_more() -> None:
    assert fallback_prose(_LeadRunCapture()) == (
        "I couldn't produce a response for this turn. Please rephrase or provide "
        "more context and I'll try again."
    )


def test_a_turn_that_answered_keeps_its_answer_although_a_chunk_carried_an_error() -> (
    None
):
    """An error chunk the run recovered from must not replace the reply."""
    capture = _failed(str(_RATE_LIMIT))
    answered = LeadResponse(prose="Here are the 132 genes.", strategy_changed=True)
    capture.response = answered

    assert final_reply(capture, changed=True) is answered


def test_a_turn_with_no_reply_at_all_gets_the_failure_reply() -> None:
    reply = final_reply(_failed("peer closed connection"), changed=False)

    assert reply is not None
    assert reply.prose.startswith("I stopped this turn on an error")
    assert reply.strategy_changed is False
