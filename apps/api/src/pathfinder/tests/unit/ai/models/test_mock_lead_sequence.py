"""The build journey the Lead's arcs share: the answer a verification decides, the
refusal a thread with a strategy gives, and the classification each turn makes."""

from __future__ import annotations

import contextvars
import re

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from pathfinder.ai.lead.build_messages import build_would_replace_the_strategy
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.models.mock import role_script
from pathfinder.ai.models.mock.kept_arcs import consult, recap
from pathfinder.ai.models.mock.lead_flow import (
    BUILD_REFUSED_MARKER,
    FEEDBACK_PROSE,
    SUCCESS_PROSE,
    build_journey,
)

_BUILD = "Find signal peptide genes [[arc:single]]"
# The question a build that would replace the strategy ends on.
_WHICH_STEPS = (
    "Which steps do you want me to change, or should I clear the strategy and "
    "start over?"
)


def _user(text: str) -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _names(seq: list[ToolCallPart]) -> list[str]:
    return [c.tool_name for c in seq]


def _exchange(tool: str, content: object, call_id: str) -> list[ModelMessage]:
    return [
        ModelResponse(
            parts=[ToolCallPart(tool_name=tool, args={}, tool_call_id=call_id)]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(tool_name=tool, content=content, tool_call_id=call_id)
            ]
        ),
    ]


def _refused(tool: str, content: str, call_id: str) -> list[ModelMessage]:
    return [
        ModelResponse(
            parts=[ToolCallPart(tool_name=tool, args={}, tool_call_id=call_id)]
        ),
        ModelRequest(
            parts=[
                RetryPromptPart(content=content, tool_name=tool, tool_call_id=call_id)
            ]
        ),
    ]


def _prose(seq: list[ToolCallPart]) -> str:
    return str(seq[-1].args_as_dict()["prose"])


def _verified(success: bool) -> list[ModelMessage]:
    return [
        _user(_BUILD),
        *_exchange("classify_user_intent", "ok", "c1"),
        *_exchange("frame_problem", {"summary": "framed"}, "f1"),
        *_exchange("build_strategy", {"outcome": {"nodeResults": []}}, "b1"),
        *_exchange("verify_strategy", {"digest": {"success": success}}, "v1"),
        *_exchange("get_live_strategy_state", {"rootCount": 479}, "l1"),
    ]


def _refused_build_turn() -> list[ModelMessage]:
    """A turn that classified, framed, called build_strategy and was refused."""
    return [
        _user(_BUILD),
        *_exchange("classify_user_intent", "ok", "c1"),
        *_exchange("frame_problem", "Structure set: 3 criteria", "f1"),
        *_refused("build_strategy", build_would_replace_the_strategy(1), "b1"),
    ]


def _lead_call(messages: list[ModelMessage], text: str = _BUILD) -> ToolCallPart:
    def run() -> ToolCallPart:
        bind_scripted_scope("plasmodb", text)
        return role_script("lead")(messages)

    return contextvars.copy_context().run(run)


def test_a_verification_that_passes_is_answered_with_the_success() -> None:
    seq = build_journey(_verified(success=True))

    assert _prose(seq) == f"{SUCCESS_PROSE} The strategy returns 479 genes."
    assert seq[-1].args_as_dict()["nextState"] == "complete"


def test_a_verification_that_fails_is_answered_with_the_zero() -> None:
    seq = build_journey(_verified(success=False))

    assert _prose(seq) == f"{FEEDBACK_PROSE} The strategy returns 479 genes."
    assert seq[-1].args_as_dict()["nextState"] == "await_user"


def test_the_feedback_prose_states_the_failure_and_not_the_success() -> None:
    assert not re.search(
        r"verified end-to-end|root size", FEEDBACK_PROSE, re.IGNORECASE
    )
    assert not re.search(r"returned 0|too narrow|relax", SUCCESS_PROSE, re.IGNORECASE)


def test_the_classification_is_made_once_per_turn() -> None:
    """A second turn re-classifies; the run's first classification is not reused."""
    second_turn: list[ModelMessage] = [
        _user(_BUILD),
        *_exchange("classify_user_intent", "ok", "c0"),
        _user("Change the range [[arc:edit-param]]"),
    ]

    call = _lead_call(second_turn, "Change the range [[arc:edit-param]]")

    assert call.tool_name == "classify_user_intent"


def test_the_mock_reads_the_real_refusal_message() -> None:
    assert BUILD_REFUSED_MARKER in build_would_replace_the_strategy(1)


def test_a_refused_build_stops_before_verification() -> None:
    seq = build_journey(_refused_build_turn())

    assert _names(seq) == [
        "classify_user_intent",
        "frame_problem",
        "build_strategy",
        "final_result",
    ]


def test_the_refused_build_asks_what_to_change_and_claims_no_success() -> None:
    prose = _prose(build_journey(_refused_build_turn()))

    assert prose.endswith(_WHICH_STEPS)
    assert "edit_strategy" not in prose
    assert not re.search(r"verified end-to-end|root size", prose, re.IGNORECASE)
    assert not re.search(r"returned 0|too narrow", prose, re.IGNORECASE)


def test_the_refused_build_leaves_the_turn_with_the_user() -> None:
    seq = build_journey(_refused_build_turn())

    assert seq[-1].args_as_dict()["nextState"] == "await_user"


def test_the_script_answers_the_refusal_instead_of_verifying() -> None:
    assert _lead_call(_refused_build_turn()).tool_name == "final_result"


def test_a_refused_consult_resume_reports_the_refusal_too() -> None:
    msgs: list[ModelMessage] = [
        _user("Consult me first [[arc:consult]]"),
        *_exchange("consult_user", "answered", "c0"),
        *_refused("build_strategy", build_would_replace_the_strategy(2), "b1"),
    ]

    assert _prose(consult(msgs)).endswith(_WHICH_STEPS)


def test_an_earlier_turns_refusal_does_not_bend_the_next_turn() -> None:
    msgs: list[ModelMessage] = [
        *_refused_build_turn(),
        ModelResponse(
            parts=[ToolCallPart(tool_name="final_result", args={}, tool_call_id="r1")]
        ),
        _user(_BUILD),
    ]

    assert _names(build_journey(msgs)) == [
        "classify_user_intent",
        "frame_problem",
        "build_strategy",
        "verify_strategy",
        "get_live_strategy_state",
        "final_result",
    ]


def test_a_retry_from_another_tool_does_not_stop_the_build_arc() -> None:
    msgs: list[ModelMessage] = [
        _user(_BUILD),
        *_refused("frame_problem", "FRAME bound nothing.", "f1"),
    ]

    assert "verify_strategy" in _names(build_journey(msgs))


def test_the_recap_answers_with_the_section_and_the_count_it_read() -> None:
    msgs: list[ModelMessage] = [
        _user("Recap [[arc:recap]]"),
        *_exchange("read_ledger_section", "## Frame (full)\n- goal: kinases", "r1"),
        *_exchange("get_live_strategy_state", {"rootCount": 363}, "l1"),
    ]

    assert _prose(recap(msgs)) == (
        "This conversation already carries: ## Frame (full)\n- goal: kinases\n\n"
        "The strategy returns 363 genes."
    )
