from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from assistant_core.graph.turn_state import UserQuestionAnswer
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field
from pydantic_ai.ui.vercel_ai.request_types import (
    DataUIPart,
    TextUIPart,
    ToolApprovalResponded,
    ToolApprovalRespondedPart,
    UIMessage,
)

from pathfinder.ai.conversation.request_body import ChatRequestBody

_USER_QUESTION_ANSWERS_TYPE = "data-user-question-answers"


class GateOption(CamelModel):
    label: str
    recommended: bool = False


class GateConsultQuestion(CamelModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    prompt: str = ""
    kind: str = "single_choice"
    options: list[GateOption] = Field(default_factory=list)


class GateDurableTask(CamelModel):
    """One worker task a suspended turn waits on."""

    task_id: str
    task_tool: str


class Gate(CamelModel):
    """The single pending interaction a turn is blocked on - the CLI's mirror
    of whatever the UI would render (approval card, consult carousel, or a
    running durable task). ``kind == "none"`` means the turn completed."""

    kind: str = "none"
    tool: str | None = None
    tool_call_id: str | None = None
    consult_questions: list[GateConsultQuestion] = Field(default_factory=list)
    tasks: list[GateDurableTask] = Field(default_factory=list)
    message: str = ""


def detect_gate(
    *,
    pending_approval: tuple[str, str] | None,
    tool_args: dict[str, dict[str, Any]],
    durable_tasks: list[tuple[str, str]],
) -> Gate:
    """Classify the pending interaction from captured turn state."""

    if durable_tasks:
        tasks = [
            GateDurableTask(task_id=task_id, task_tool=task_tool)
            for task_id, task_tool in durable_tasks
        ]
        running = ", ".join(f"{t.task_tool} ({t.task_id})" for t in tasks)
        return Gate(
            kind="durable",
            tasks=tasks,
            message=f"durable tasks running: {running}",
        )
    if pending_approval is None:
        return Gate(kind="none", message="turn complete")
    tool, call_id = pending_approval
    if tool == "consult_user":
        raw = (tool_args.get(call_id) or {}).get("questions") or []
        questions = [GateConsultQuestion.model_validate(q) for q in raw]
        return Gate(
            kind="consult",
            tool=tool,
            tool_call_id=call_id,
            consult_questions=questions,
            message=f"consult_user: {len(questions)} question(s) to answer",
        )
    return Gate(
        kind="approval",
        tool=tool,
        tool_call_id=call_id,
        message=f"approval: {tool} - approve or deny",
    )


def _approval_part(
    *, tool: str, tool_call_id: str, approved: bool, reason: str | None
) -> ToolApprovalRespondedPart:
    return ToolApprovalRespondedPart(
        type=f"tool-{tool}",
        tool_call_id=tool_call_id,
        approval=ToolApprovalResponded(
            id=tool_call_id, approved=approved, reason=reason
        ),
    )


def _data_part(*, part_type: str, tool_call_id: str, answers: list[Any]) -> DataUIPart:
    return DataUIPart(
        type=part_type,
        id=str(uuid4()),
        data={
            "toolCallId": tool_call_id,
            "answers": [a.model_dump(by_alias=True, mode="json") for a in answers],
        },
    )


class BodyCtx(CamelModel):
    """The conversation-scoped fields every resume body needs - bundled so the
    builders stay under the argument limit."""

    conversation_id: UUID
    site_id: str
    mode: str = "strategy"
    phase_models: dict[str, str] = Field(default_factory=dict)


def _body(ctx: BodyCtx, message: UIMessage) -> ChatRequestBody:
    return ChatRequestBody(
        conversation_id=ctx.conversation_id,
        site_id=ctx.site_id,
        mode=ctx.mode,
        phase_models=ctx.phase_models,
        messages=[message],
    )


def user_body(ctx: BodyCtx, *, message_id: UUID, text: str) -> ChatRequestBody:
    return _body(
        ctx,
        UIMessage(id=str(message_id), role="user", parts=[TextUIPart(text=text)]),
    )


def approval_body(
    ctx: BodyCtx,
    *,
    message_id: UUID,
    tool: str,
    tool_call_id: str,
    approved: bool,
    reason: str | None = None,
) -> ChatRequestBody:
    return _body(
        ctx,
        UIMessage(
            id=str(message_id),
            role="assistant",
            parts=[
                _approval_part(
                    tool=tool,
                    tool_call_id=tool_call_id,
                    approved=approved,
                    reason=reason,
                )
            ],
        ),
    )


def consult_body(
    ctx: BodyCtx,
    *,
    message_id: UUID,
    tool_call_id: str,
    answers: list[UserQuestionAnswer],
) -> ChatRequestBody:
    return _body(
        ctx,
        UIMessage(
            id=str(message_id),
            role="assistant",
            parts=[
                _approval_part(
                    tool="consult_user",
                    tool_call_id=tool_call_id,
                    approved=True,
                    reason=None,
                ),
                _data_part(
                    part_type=_USER_QUESTION_ANSWERS_TYPE,
                    tool_call_id=tool_call_id,
                    answers=answers,
                ),
            ],
        ),
    )
