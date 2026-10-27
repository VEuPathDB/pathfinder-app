"""Why a FRAME pass that stops on the user asks about a slot its draft lacks."""

from __future__ import annotations

from collections.abc import Sequence

from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.domain.strategy.card_answers import params_held
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.questions import SlotQuestion

# How many of the pass's questions the refusal prints back to it.
_ASKED_WINDOW = 4


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
        f"null for the parameter the user must decide. If no search on this site "
        f"can answer the requirement, or it needs the analysis workflow, report "
        f"it in requirement_problems and ask no question about it."
    )


def questions_that_bind_to_nothing(result: FrameResult, draft: OperationalSpec) -> str:
    """Why a pass that stops on the user asks about a slot no criterion of the
    draft holds, or "". A slot question binds its criterion's parameter."""
    return _unheld_slot_questions(result.open_questions, draft)
