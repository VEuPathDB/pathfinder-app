"""Why a FRAME pass that stops on the user asks about nothing it recorded."""

from __future__ import annotations

from collections.abc import Sequence

from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.domain.strategy.card_answers import params_held
from pathfinder.domain.strategy.constraints import message_states
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.questions import SlotQuestion

# How many of the pass's questions the refusal prints back to it.
_ASKED_WINDOW = 4


def _holds_an_open_slot(spec: OperationalSpec) -> bool:
    return bool(spec.open_slots) or any(c.open_params for c in spec.criteria)


def _unheld_slot_questions(
    questions: Sequence[SlotQuestion], draft: OperationalSpec
) -> str:
    """Why a question names a slot no criterion of the draft holds, or empty."""
    held = params_held(draft)
    unheld = [
        q
        for q in questions
        if (q.criterion_id or q.param_name)
        and q.param_name not in held.get(q.criterion_id, set())
    ]
    if not unheld:
        return ""
    named = "; ".join(
        f"{q.question!r} names {q.criterion_id or '?'}.{q.param_name or '?'}"
        for q in unheld[:_ASKED_WINDOW]
    )
    holds = "; ".join(
        f"{cid}: {', '.join(sorted(params))}" for cid, params in held.items() if params
    )
    return (
        f"FRAME ended needs_user with options that bind nothing: {named}. An option "
        f"sets the parameter its question names, so each question names a "
        f"criterion_id and param_name the draft holds. The draft holds {holds or 'none'}. "
        f"Name one of those, or record the criterion first with set_criterion and "
        f"null for the parameter the user must decide."
    )


def questions_that_bind_to_nothing(
    result: FrameResult,
    draft: OperationalSpec,
    found: OperationalSpec | None,
) -> str:
    """Why a pass that stops on the user asks about nothing it recorded, or "".

    A slot question binds its criterion's parameter, a question on an unstated
    requirement binds through drop and keep, and any other needs an open slot."""
    questions = result.open_questions
    unheld = _unheld_slot_questions(questions, draft)
    if unheld:
        return unheld
    free = [
        q
        for q in questions
        if not q.names_a_slot
        and not any(message_states(q.question, text) for text in result.unstated)
    ]
    if not free:
        return ""
    if found is not None and draft == found:
        reason = "the spec is exactly as this dispatch found it"
    elif not _holds_an_open_slot(draft):
        reason = "no criterion of the spec holds an open slot"
    else:
        return ""
    asked = "; ".join(q.question for q in free[:_ASKED_WINDOW])
    return (
        f"FRAME ended needs_user with {len(free)} question(s) ({asked}) and "
        f"{reason}, so an answer has nowhere to land and the next turn reads no "
        f"criterion to bind it into. Call set_criterion for the criterion each "
        f"question is about, with its search, the values you already have, and "
        f"null for every parameter the user must decide, which records that "
        f"parameter as an open slot. A question about which strategy the user "
        f"saved is recorded the same way: call set_criterion with "
        f"saved_strategy set to the name the user gave, which records the "
        f"saved_strategy slot with the names the listing holds. Then end "
        f"needs_user with the same questions."
    )
