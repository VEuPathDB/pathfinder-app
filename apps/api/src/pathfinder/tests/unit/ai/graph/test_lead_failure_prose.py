"""What a turn that failed tells the user, and what it keeps out of the thread.

The reply names the shape of the failure. A provider's response body, a header
and a url with a query are the provider's, not the reader's, and the reply is
persisted and read back on the next turn.
"""

from __future__ import annotations

from pydantic_ai.exceptions import ModelHTTPError

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_stops import (
    MAX_FAILURE_CLAUSE_CHARS,
    fallback_prose,
    final_reply,
)
from pathfinder.ai.lead.sub_agent_tools import UnansweredStage
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


_CHOSEN_MODEL = "openai:gpt-5.6-luna"
_CHOSEN_MODEL_NAME = "GPT-5.6 Luna"


def _failed(error: str) -> _LeadRunCapture:
    capture = _LeadRunCapture()
    capture.run_error = error
    return capture


def _never_answered(error: str, *, model: str = _CHOSEN_MODEL) -> _LeadRunCapture:
    """A turn whose model was asked and streamed nothing before the error."""
    capture = _failed(error)
    capture.lead_model = model
    return capture


def _after_the_lead_answered(error: str) -> _LeadRunCapture:
    """A turn whose own model answered, so the failure came from a dispatch."""
    capture = _failed(error)
    capture.lead_model = _CHOSEN_MODEL
    capture.model_answered = True
    return capture


def _stage(role: PhaseRole, model: str = _CHOSEN_MODEL) -> UnansweredStage:
    return UnansweredStage(role=role, model_id=model)


def _stage_named(prose: str) -> str:
    """The stage word the reply uses, taken out of its sentence."""
    said, _, _ = prose.partition(" stage of this turn")
    return said.rsplit("The ", 1)[1]


def test_a_provider_error_names_its_status_and_not_its_body() -> None:
    prose = fallback_prose(_failed(str(_RATE_LIMIT)), None)

    assert prose == (
        "I stopped this turn on an error I could not recover from: the model "
        "provider answered 429. Send the message again and I will start over "
        "from it."
    )
    assert _ORG not in prose
    assert "body" not in prose


def test_a_transport_failure_still_names_what_happened() -> None:
    prose = fallback_prose(_failed("peer closed connection"), None)

    assert prose == (
        "I stopped this turn on an error I could not recover from: peer closed "
        "connection. Send the message again and I will start over from it."
    )


def test_a_url_with_a_query_is_not_read_back_to_the_user() -> None:
    prose = fallback_prose(
        _failed("request to https://api.example/v1/chat?key=sk-live-9f2 failed"),
        None,
    )

    assert "https://" not in prose
    assert "sk-live-9f2" not in prose
    assert "request to failed" in prose


def test_a_failure_that_is_only_a_payload_still_says_the_run_failed() -> None:
    prose = fallback_prose(_failed('{"error": {"message": "nope"}}'), None)

    assert "nope" not in prose
    assert "the run failed" in prose


def test_a_long_failure_is_cut_to_one_clause() -> None:
    words = " ".join(["overload"] * 60)
    prose = fallback_prose(_failed(f"{words}\nsecond line"), None)

    assert "second line" not in prose
    assert len(prose) < len(words)
    assert prose.count("overload") <= MAX_FAILURE_CLAUSE_CHARS // len("overload ") + 1


def test_a_run_that_ended_without_a_reply_and_without_an_error_asks_for_more() -> None:
    assert fallback_prose(_LeadRunCapture(), None) == (
        "I couldn't produce a response for this turn. Please rephrase or provide "
        "more context and I'll try again."
    )


class TestTheModelTheTurnCouldNotReach:
    """A model that never answered is named, with the stage that chose it."""

    def test_the_reply_names_the_model_and_its_stage(self) -> None:
        prose = fallback_prose(_never_answered("Connection error."), None)

        assert prose == (
            "I stopped this turn on an error I could not recover from: "
            "Connection error. The Assistant stage of this turn runs "
            "GPT-5.6 Luna, and it did not answer. Choose a different model for "
            "that stage in Settings, or send the message again and I will "
            "start over from it."
        )

    def test_naming_the_model_brings_no_response_body_with_it(self) -> None:
        prose = fallback_prose(_never_answered(str(_RATE_LIMIT)), None)

        assert prose == (
            "I stopped this turn on an error I could not recover from: the "
            "model provider answered 429. The Assistant stage of this turn "
            "runs GPT-5.6 Luna, and it did not answer. Choose a different "
            "model for that stage in Settings, or send the message again and "
            "I will start over from it."
        )
        assert _ORG not in prose
        assert "Rate limit reached" not in prose
        assert "https://" not in prose

    def test_naming_the_model_brings_no_url_with_a_query_with_it(self) -> None:
        prose = fallback_prose(
            _never_answered(
                "request to https://api.example/v1/chat?key=sk-live-9f2 failed",
            ),
            None,
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from: request "
            "to failed. The Assistant stage of this turn runs GPT-5.6 Luna, "
            "and it did not answer. Choose a different model for that stage in "
            "Settings, or send the message again and I will start over from it."
        )
        assert "sk-live-9f2" not in prose

    def test_a_model_that_answered_before_the_failure_is_not_blamed(self) -> None:
        capture = _never_answered("peer closed connection")
        capture.model_answered = True

        assert fallback_prose(capture, None) == (
            "I stopped this turn on an error I could not recover from: peer "
            "closed connection. Send the message again and I will start over "
            "from it."
        )

    def test_a_model_no_researcher_could_have_chosen_keeps_the_terse_shape(
        self,
    ) -> None:
        """The catalog is what a stage picker offers, so nothing else is a choice."""
        prose = fallback_prose(
            _never_answered("Connection error.", model="mock:lead"), None
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from: "
            "Connection error. Send the message again and I will start over "
            "from it."
        )
        assert _CHOSEN_MODEL_NAME not in prose


class TestTheSubAgentStageTheTurnCouldNotReach:
    """A dispatch whose model never answered names that stage, not the Lead's."""

    def test_the_reply_names_the_stage_the_dispatch_ran(self) -> None:
        prose = fallback_prose(
            _after_the_lead_answered("Connection error."), _stage("frame")
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from: "
            "Connection error. The Planning stage of this turn runs "
            "GPT-5.6 Luna, and it did not answer. Choose a different model for "
            "that stage in Settings, or send the message again and I will "
            "start over from it."
        )

    def test_every_stage_reads_as_the_name_the_settings_tab_shows(self) -> None:
        named = [
            _stage_named(
                fallback_prose(
                    _after_the_lead_answered("Connection error."), _stage(role)
                ),
            )
            for role in ("lead", "frame", "execution", "verification")
        ]

        assert named == ["Assistant", "Planning", "Building", "Checking"]

    def test_naming_the_stage_brings_no_response_body_with_it(self) -> None:
        prose = fallback_prose(
            _after_the_lead_answered(str(_RATE_LIMIT)), _stage("verification")
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from: the "
            "model provider answered 429. The Checking stage of this turn "
            "runs GPT-5.6 Luna, and it did not answer. Choose a different "
            "model for that stage in Settings, or send the message again and "
            "I will start over from it."
        )
        assert _ORG not in prose
        assert "Rate limit reached" not in prose
        assert "https://" not in prose

    def test_naming_the_stage_brings_no_url_with_a_query_with_it(self) -> None:
        prose = fallback_prose(
            _after_the_lead_answered(
                "request to https://api.example/v1/chat?key=sk-live-9f2 failed",
            ),
            _stage("execution"),
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from: request "
            "to failed. The Building stage of this turn runs GPT-5.6 Luna, "
            "and it did not answer. Choose a different model for that stage in "
            "Settings, or send the message again and I will start over from it."
        )
        assert "sk-live-9f2" not in prose

    def test_a_failure_after_every_model_answered_keeps_the_terse_shape(self) -> None:
        prose = fallback_prose(_after_the_lead_answered("peer closed connection"), None)

        assert prose == (
            "I stopped this turn on an error I could not recover from: peer "
            "closed connection. Send the message again and I will start over "
            "from it."
        )

    def test_a_stage_model_outside_the_catalog_keeps_the_terse_shape(self) -> None:
        prose = fallback_prose(
            _after_the_lead_answered("Connection error."),
            _stage("frame", "mock:frame"),
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from: "
            "Connection error. Send the message again and I will start over "
            "from it."
        )
        assert "Planning" not in prose


def test_a_turn_that_answered_keeps_its_answer_although_a_chunk_carried_an_error() -> (
    None
):
    """An error chunk the run recovered from must not replace the reply."""
    capture = _failed(str(_RATE_LIMIT))
    answered = LeadResponse(prose="Here are the 132 genes.", strategy_changed=True)
    capture.response = answered

    assert final_reply(capture, None, changed=True) is answered


def test_a_turn_with_no_reply_at_all_gets_the_failure_reply() -> None:
    reply = final_reply(_failed("peer closed connection"), None, changed=False)

    assert reply is not None
    assert reply.prose.startswith("I stopped this turn on an error")
    assert reply.strategy_changed is False
