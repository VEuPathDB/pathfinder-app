"""The contract rule over an edit turn that asks for a change and makes none."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reply
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)

_REMOVAL = (
    "One gene is too few to be meaningful. Remove whichever step you added last "
    "and tell me what the count goes back to."
)
_HYPHAL = Constraint(
    kind=ConstraintKind.OTHER,
    label="hyphal growth expression",
    requested_value="expressed during hyphal growth",
)
_CHANGED_NOTHING = (
    'The final step "Intersect" holds the result of the five steps. '
    "This turn changed nothing."
)
_REFUSED = (
    "The message asks to remove 'expressed during hyphal growth' and this turn "
    "made no change and raised no card: remove it through delete_step, or say "
    "in the reply why it cannot be removed."
)


def _deps(intent: UserIntent) -> LeadDeps:
    deps = lead_deps(
        pipeline_state("fungidb", user_prompt=_REMOVAL, user_message_id=uuid4()),
        intent=intent,
        strategy_session=session_with_one_step(),
    )
    deps.state.turn_markers.intent_classified = True
    return deps


def _removal() -> UserIntent:
    return UserIntent(
        classification=IntentClassification.EDIT_STRATEGY,
        inferred_goal="Remove the last step added and report the count.",
        edit_direction="loosen",
        withdrawn=[_HYPHAL],
    )


def _found(
    deps: LeadDeps, prose: str, *, on_a_card: bool = False
) -> list[tuple[str, str]]:
    record = turn_record(run_context_for(deps)).model_copy(
        update={"ends_on_a_card": on_a_card}
    )
    return [(m.kind, m.sentence) for m in reconcile(reply(prose), record)]


def test_an_edit_that_removes_nothing_and_raises_no_card_is_refused() -> None:
    assert _found(_deps(_removal()), _CHANGED_NOTHING) == [("unmade_change", _REFUSED)]


def test_the_same_edit_that_ends_on_a_delete_card_stands() -> None:
    assert _found(_deps(_removal()), _CHANGED_NOTHING, on_a_card=True) == []


def test_a_follow_up_question_that_changes_nothing_stands() -> None:
    question = UserIntent(
        classification=IntentClassification.FOLLOW_UP_QUESTION,
        inferred_goal="Report the count.",
        withdrawn=[_HYPHAL],
    )

    assert _found(_deps(question), _CHANGED_NOTHING) == []


def test_an_edit_whose_reply_says_why_the_step_cannot_be_removed_stands() -> None:
    prose = (
        "The step expressed during hyphal growth cannot be removed on its own: "
        "the intersect above it needs two inputs, so removing it drops the "
        "whole branch."
    )

    assert _found(_deps(_removal()), prose) == []


def test_an_edit_that_states_a_value_and_makes_no_change_is_refused() -> None:
    stated = Constraint(
        kind=ConstraintKind.OTHER, label="fold change", requested_value="fold change 4"
    )
    intent = UserIntent(
        classification=IntentClassification.EDIT_STRATEGY,
        inferred_goal="Raise the fold change cut.",
        explicit_constraints=[stated],
    )

    assert _found(_deps(intent), _CHANGED_NOTHING) == [
        (
            "unmade_change",
            (
                "The message asks for 'fold change 4' and this turn made no "
                "change and raised no card: make it through edit_strategy, or "
                "say in the reply why it cannot be made."
            ),
        )
    ]
