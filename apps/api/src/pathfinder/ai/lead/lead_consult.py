"""The Lead's consult tool, and the requirements the answers become."""

from __future__ import annotations

from assistant_core.graph.tool_summary import with_summary
from assistant_core.graph.turn_state import ConsultQuestion, UserQuestionAnswer
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import (
    CombinationRequest,
    Constraint,
    ConstraintKind,
    ConstraintSource,
)

_LABEL_LIMIT = 120


def _answer_requirements(answers: list[UserQuestionAnswer]) -> list[Constraint]:
    """The answers as requirements, one per answer that states a value.

    An answer that reads as a combination expression is typed as one, so the
    structure gate and the verification hold can check it.
    """
    requirements: list[Constraint] = []
    for answer in answers:
        stated = (
            "; ".join(answer.chosen_labels) if answer.chosen_labels else answer.note
        )
        if not stated:
            continue
        expression = next(
            (
                text
                for text in (*answer.chosen_labels, answer.note)
                if CombinationRequest.parse(text) is not None
            ),
            None,
        )
        requirements.append(
            Constraint(
                kind=(
                    ConstraintKind.OTHER
                    if expression is None
                    else ConstraintKind.COMBINATION
                ),
                requested_value=expression or stated,
                # A question carries the label. An unlabelled one falls back to
                # the answer, because a requirement is always named.
                label=answer.prompt[:_LABEL_LIMIT] or stated[:_LABEL_LIMIT],
                source=ConstraintSource.USER_EXPLICIT,
                hard=True,
            )
        )
    return requirements


def _format_answers(answers: list[UserQuestionAnswer]) -> str:
    parts: list[str] = []
    for a in answers:
        chosen = ", ".join(a.chosen_labels) if a.chosen_labels else "(free text)"
        line = f'"{a.prompt}" -> {chosen}'
        if a.note:
            line += f" - note: {a.note}"
        parts.append(line)
    return "; ".join(parts)


async def consult_user(
    ctx: RunContext[LeadDeps],
    questions: list[ConsultQuestion],
) -> ToolReturn[list[UserQuestionAnswer]]:
    """Ask the user design questions that SHAPE the investigation, before a
    plan is built. Use this whenever a real fork exists - which searches to
    combine, a threshold that changes the steps, whether to add an arm -
    instead of guessing or bundling the choice into plan approval.

    This pauses the turn: the user answers each question in a carousel
    (options + optional free-text note). Their answers are returned to you
    here so you can run (or re-run) ``frame_problem``, or ``edit_strategy``
    over a strategy that holds a step, with them as hard constraints. Ask only the few questions that genuinely change the
    answer; pick sensible defaults for everything else and state your
    assumptions in prose. Do NOT ask "submit or request changes?" - the
    approval card already offers both. Background for a question goes in
    that question's ``context``; the call itself takes only ``questions``.
    """
    state = ctx.deps.state
    pending = state.pending_approval
    answers = (
        list(state.user_question_answers.get(pending.tool_call_id, []))
        if pending is not None
        else []
    )
    asked = with_summary(
        answers,
        f"{len(questions)} questions asked",
        ctx=ctx,
    )
    if answers:
        # Their answers are new requirements, so one more frame is licensed.
        state.turn_markers.framed = False
        state.turn_markers.consulted = True
        state.domain.record_requirements(_answer_requirements(answers))
        state.domain.answer_open_questions(_format_answers(answers), on_card=True)
    # A strategy that holds a step takes the answers as an edit.
    tool = "edit_strategy" if ctx.deps.step_count else "frame_problem"
    asked.content = (
        f"Presented {len(questions)} question(s); awaiting the user's answers."
        if not answers
        else (
            f"The user answered your questions: {_format_answers(answers)}. "
            f"Now run {tool} honoring these as hard constraints."
        )
    )
    return asked
