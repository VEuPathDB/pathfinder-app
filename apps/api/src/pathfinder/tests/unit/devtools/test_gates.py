from __future__ import annotations

from uuid import uuid4

from assistant_core.graph.turn_state import UserQuestionAnswer
from pydantic import TypeAdapter
from pydantic_ai.ui.vercel_ai.request_types import (
    DataUIPart,
    ToolApprovalResponded,
    ToolApprovalRespondedPart,
)

from pathfinder.devtools.gates import (
    BodyCtx,
    approval_body,
    consult_body,
    detect_gate,
)

_CTX = BodyCtx(conversation_id=uuid4(), site_id="vectorbase", mode="strategy")


def _typed[T](value: object, shape: type[T]) -> T:
    """A value of a wide union type, as the class the builder puts there."""
    return TypeAdapter(shape).validate_python(value)


def test_detect_none_when_no_pending() -> None:
    gate = detect_gate(pending_approval=None, tool_args={}, durable_tasks=[])
    assert gate.kind == "none"


def test_detect_generic_approval() -> None:
    gate = detect_gate(
        pending_approval=("delete_step", "c1"),
        tool_args={},
        durable_tasks=[],
    )
    assert gate.kind == "approval"
    assert gate.tool == "delete_step"
    assert gate.tool_call_id == "c1"


def test_detect_consult_parses_questions() -> None:
    gate = detect_gate(
        pending_approval=("consult_user", "c2"),
        tool_args={
            "c2": {
                "questions": [
                    {
                        "id": "strain",
                        "prompt": "Which strain?",
                        "kind": "single_choice",
                        "options": [
                            {"label": "Liverpool", "recommended": True},
                            {"label": "Rockefeller"},
                        ],
                    }
                ]
            }
        },
        durable_tasks=[],
    )
    assert gate.kind == "consult"
    assert gate.tool_call_id == "c2"
    assert gate.consult_questions[0].id == "strain"
    assert gate.consult_questions[0].options[0].label == "Liverpool"
    assert gate.consult_questions[0].options[0].recommended is True


def test_detect_durable_task() -> None:
    gate = detect_gate(
        pending_approval=None,
        tool_args={},
        durable_tasks=[("task-123", "optimize_search_parameters")],
    )
    assert gate.kind == "durable"
    assert [t.task_id for t in gate.tasks] == ["task-123"]
    assert [t.task_tool for t in gate.tasks] == ["optimize_search_parameters"]


def test_detect_names_every_task_one_step_handed_to_the_worker() -> None:
    gate = detect_gate(
        pending_approval=None,
        tool_args={},
        durable_tasks=[
            ("task-1", "run_control_tests_on_step"),
            ("task-2", "run_control_tests_on_step"),
        ],
    )
    assert [t.task_id for t in gate.tasks] == ["task-1", "task-2"]
    assert gate.message == (
        "durable tasks running: run_control_tests_on_step (task-1), "
        "run_control_tests_on_step (task-2)"
    )


def test_approval_body_builds_responded_part() -> None:
    body = approval_body(
        _CTX,
        message_id=uuid4(),
        tool="delete_step",
        tool_call_id="c1",
        approved=False,
        reason="not now",
    )
    msg = body.messages[0]
    assert msg.role == "assistant"
    part = _typed(msg.parts[0], ToolApprovalRespondedPart)
    assert part.type == "tool-delete_step"
    approval = _typed(part.approval, ToolApprovalResponded)
    assert approval.approved is False
    assert approval.reason == "not now"


def test_consult_body_has_approval_and_answers() -> None:
    answers = [
        UserQuestionAnswer(
            question_id="strain", prompt="Which strain?", chosen_labels=["Liverpool"]
        )
    ]
    body = consult_body(_CTX, message_id=uuid4(), tool_call_id="c2", answers=answers)
    message = body.messages[0]
    types = [p.type for p in message.parts]
    assert "tool-consult_user" in types
    assert "data-user-question-answers" in types
    data_part = _typed(
        message.parts[types.index("data-user-question-answers")], DataUIPart
    )
    assert data_part.data["toolCallId"] == "c2"
    assert data_part.data["answers"][0]["chosenLabels"] == ["Liverpool"]
