"""What a turn that failed tells the user, and what it keeps out of the thread.

The reply says the turn stopped and points at the refusal the facts part shows
whole. A provider's response body never reaches the reply, which is persisted
and read back on the next turn, and a link's query never reaches either.
"""

from __future__ import annotations

from pydantic_ai.exceptions import ModelHTTPError

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_stops import (
    fallback_prose,
    final_reply,
    shown_refusal,
)
from pathfinder.ai.lead.sub_agent_tools import UnansweredStage
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.tests._support.models import DEFAULT_MODEL, display_name

_ORG = "org-abc123"
_RATE_LIMIT = ModelHTTPError(
    status_code=429,
    model_name=DEFAULT_MODEL.partition(":")[2],
    body={
        "error": {
            "message": f"Rate limit reached for {_ORG} on tokens",
            "type": "tokens",
            "docs": "https://platform.example/limits?org=abc123",
        },
    },
)


_CHECKED = (
    "The change shown beside this reply landed and was checked; what the check "
    "found is shown beside it."
)

_CHOSEN_MODEL = DEFAULT_MODEL
_CHOSEN_MODEL_NAME = display_name(DEFAULT_MODEL)


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
    prose = fallback_prose(_failed(str(_RATE_LIMIT)), None, change="unchanged")

    assert prose == (
        "I stopped this turn on an error I could not recover from; what it "
        "answered is shown beside this reply. Send the message again and I "
        "will start over from it."
    )
    assert _ORG not in prose
    assert "body" not in prose


def test_a_transport_failure_still_names_what_happened() -> None:
    prose = fallback_prose(_failed("peer closed connection"), None, change="unchanged")

    assert prose == (
        "I stopped this turn on an error I could not recover from; what it "
        "answered is shown beside this reply. Send the message again and I "
        "will start over from it."
    )


def test_the_refusal_is_shown_whole_without_a_link_s_query() -> None:
    words = " ".join(["overload"] * 60)
    error = f"request to https://api.example/v1/chat?key=sk-live-9f2 failed {words}"

    assert shown_refusal(error) == (
        f"request to https://api.example/v1/chat failed {words}"
    )


def test_a_provider_refusal_is_shown_with_its_own_sentence() -> None:
    assert "Rate limit reached for org-abc123 on tokens" in shown_refusal(
        str(_RATE_LIMIT)
    )


def test_a_run_that_ended_without_a_reply_and_without_an_error_asks_for_more() -> None:
    assert fallback_prose(_LeadRunCapture(), None, change="unchanged") == (
        "I couldn't produce a response for this turn. Please rephrase or provide "
        "more context and I'll try again."
    )


class TestTheModelTheTurnCouldNotReach:
    """A model that never answered is named, with the stage that chose it."""

    def test_the_reply_names_the_model_and_its_stage(self) -> None:
        prose = fallback_prose(
            _never_answered("Connection error."), None, change="unchanged"
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from; what it "
            "answered is shown beside this reply. The Assistant stage of this "
            f"turn runs {_CHOSEN_MODEL_NAME}, and it did not answer. Choose a "
            "different "
            "model for that stage in Settings, or send the message again and I "
            "will start over from it."
        )

    def test_naming_the_model_brings_no_response_body_with_it(self) -> None:
        prose = fallback_prose(
            _never_answered(str(_RATE_LIMIT)), None, change="unchanged"
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from; what it "
            "answered is shown beside this reply. The Assistant stage of this "
            f"turn runs {_CHOSEN_MODEL_NAME}, and it did not answer. Choose a "
            "different "
            "model for that stage in Settings, or send the message again and I "
            "will start over from it."
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
            change="unchanged",
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from; what it "
            "answered is shown beside this reply. The Assistant stage of this "
            f"turn runs {_CHOSEN_MODEL_NAME}, and it did not answer. Choose a "
            "different "
            "model for that stage in Settings, or send the message again and I "
            "will start over from it."
        )
        assert "sk-live-9f2" not in prose

    def test_a_model_that_answered_before_the_failure_is_not_blamed(self) -> None:
        capture = _never_answered("peer closed connection")
        capture.model_answered = True

        assert fallback_prose(capture, None, change="unchanged") == (
            "I stopped this turn on an error I could not recover from; what it "
            "answered is shown beside this reply. Send the message again and I "
            "will start over from it."
        )

    def test_a_model_no_researcher_could_have_chosen_keeps_the_terse_shape(
        self,
    ) -> None:
        """The catalog is what a stage picker offers, so nothing else is a choice."""
        prose = fallback_prose(
            _never_answered("Connection error.", model="mock:lead"),
            None,
            change="unchanged",
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from; what it "
            "answered is shown beside this reply. Send the message again and I "
            "will start over from it."
        )
        assert _CHOSEN_MODEL_NAME not in prose


class TestTheSubAgentStageTheTurnCouldNotReach:
    """A dispatch whose model never answered names that stage, not the Lead's."""

    def test_the_reply_names_the_stage_the_dispatch_ran(self) -> None:
        prose = fallback_prose(
            _after_the_lead_answered("Connection error."),
            _stage("frame"),
            change="unchanged",
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from; what it "
            "answered is shown beside this reply. The Planning stage of this turn "
            f"runs {_CHOSEN_MODEL_NAME}, and it did not answer. Choose a different "
            "model "
            "for that stage in Settings, or send the message again and I will "
            "start over from it."
        )

    def test_every_stage_reads_as_the_name_the_settings_tab_shows(self) -> None:
        named = [
            _stage_named(
                fallback_prose(
                    _after_the_lead_answered("Connection error."),
                    _stage(role),
                    change="unchanged",
                ),
            )
            for role in ("lead", "frame", "execution", "verification")
        ]

        assert named == ["Assistant", "Planning", "Building", "Checking"]

    def test_naming_the_stage_brings_no_response_body_with_it(self) -> None:
        prose = fallback_prose(
            _after_the_lead_answered(str(_RATE_LIMIT)),
            _stage("verification"),
            change="unchanged",
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from; what it "
            "answered is shown beside this reply. The Checking stage of this turn "
            f"runs {_CHOSEN_MODEL_NAME}, and it did not answer. Choose a different "
            "model "
            "for that stage in Settings, or send the message again and I will "
            "start over from it."
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
            change="unchanged",
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from; what it "
            "answered is shown beside this reply. The Building stage of this turn "
            f"runs {_CHOSEN_MODEL_NAME}, and it did not answer. Choose a different "
            "model "
            "for that stage in Settings, or send the message again and I will "
            "start over from it."
        )
        assert "sk-live-9f2" not in prose

    def test_a_failure_after_every_model_answered_keeps_the_terse_shape(self) -> None:
        prose = fallback_prose(
            _after_the_lead_answered("peer closed connection"), None, change="unchanged"
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from; what it "
            "answered is shown beside this reply. Send the message again and I "
            "will start over from it."
        )

    def test_a_stage_model_outside_the_catalog_keeps_the_terse_shape(self) -> None:
        prose = fallback_prose(
            _after_the_lead_answered("Connection error."),
            _stage("frame", "mock:frame"),
            change="unchanged",
        )

        assert prose == (
            "I stopped this turn on an error I could not recover from; what it "
            "answered is shown beside this reply. Send the message again and I "
            "will start over from it."
        )
        assert "Planning" not in prose


def test_a_turn_that_answered_keeps_its_answer_although_a_chunk_carried_an_error() -> (
    None
):
    """An error chunk the run recovered from must not replace the reply."""
    capture = _failed(str(_RATE_LIMIT))
    answered = LeadResponse(prose="Here are the 132 genes.", strategy_changed=True)
    capture.response = answered

    assert final_reply(capture, None, change="unchecked") is answered


def test_a_turn_with_no_reply_at_all_gets_the_failure_reply() -> None:
    reply = final_reply(_failed("peer closed connection"), None, change="unchanged")

    assert reply is not None
    assert reply.prose.startswith("I stopped this turn on an error")
    assert reply.strategy_changed is False


class TestATurnWhoseChangeLanded:
    """A change the facts show landed is never sent again from the start."""

    def test_a_refusal_after_a_landed_delete_asks_for_the_check(self) -> None:
        prose = fallback_prose(_failed(str(_RATE_LIMIT)), None, change="unchecked")

        assert "Send the message again" not in prose
        assert "start over" not in prose
        assert prose.endswith(
            "The change shown beside this reply landed and was not checked. "
            "Ask me to check it and I will go on from there."
        )

    def test_a_model_that_did_not_answer_after_the_change_keeps_the_change(
        self,
    ) -> None:
        prose = fallback_prose(
            _never_answered("Connection error."), None, change="unchecked"
        )

        assert "Choose a different model for that stage in Settings" in prose
        assert "send the message again" not in prose
        assert prose.endswith(
            "then ask me to check the change shown beside this reply, which landed."
        )

    def test_a_run_with_no_reply_and_no_error_states_what_landed(self) -> None:
        prose = fallback_prose(_LeadRunCapture(), None, change="unchecked")

        assert "rephrase" not in prose
        assert "The change shown beside this reply landed" in prose

    def test_a_model_that_did_not_answer_after_a_checked_change_asks_to_go_on(
        self,
    ) -> None:
        prose = fallback_prose(
            _never_answered("Connection error."), None, change="checked"
        )

        assert prose.endswith(
            "then ask me to go on from the change shown beside this reply, which "
            "landed and was checked."
        )

    def test_a_change_its_check_judged_is_said_to_be_checked(self) -> None:
        prose = [
            fallback_prose(capture, None, change="checked")
            for capture in (_failed(str(_RATE_LIMIT)), _LeadRunCapture())
        ]

        assert [p.endswith(_CHECKED) and "not checked" not in p for p in prose] == [
            True,
            True,
        ]

    def test_the_reply_the_turn_writes_carries_the_change(self) -> None:
        reply = final_reply(_failed("peer closed connection"), None, change="unchecked")

        assert reply is not None
        assert reply.strategy_changed
        assert "Send the message again" not in reply.prose
