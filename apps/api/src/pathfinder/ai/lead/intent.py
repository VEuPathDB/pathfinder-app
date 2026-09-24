from __future__ import annotations

from enum import StrEnum

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field

from pathfinder.domain.strategy.constraints import (
    CONSTRAINT_KINDS,
    CombinationReading,
    CombinationRequest,
    Constraint,
    ConstraintKind,
    read_combination,
)


class IntentClassification(StrEnum):
    NEW_STRATEGY = "new_strategy"
    EXTEND_STRATEGY = "extend_strategy"
    EDIT_STRATEGY = "edit_strategy"
    FOLLOW_UP_QUESTION = "follow_up_question"
    CLARIFICATION_RESPONSE = "clarification_response"
    SLOT_ANSWER = "slot_answer"
    APPROVAL = "approval"
    DENIAL = "denial"
    OFF_TOPIC = "off_topic"
    CONTEXT_STATEMENT = "context_statement"
    MEMORY_REQUEST = "memory_request"


# The classifications that ask for a change to the strategy. Only these turns
# are offered the tools that frame, build, edit or verify one.
BUILDING_INTENTS: frozenset[IntentClassification] = frozenset(
    {
        IntentClassification.NEW_STRATEGY,
        IntentClassification.EXTEND_STRATEGY,
        IntentClassification.EDIT_STRATEGY,
        IntentClassification.CLARIFICATION_RESPONSE,
        IntentClassification.SLOT_ANSWER,
        IntentClassification.APPROVAL,
    }
)

# The classifications that state a request of their own. An answer to a
# question the assistant asked is not one of them.
REQUEST_INTENTS: frozenset[IntentClassification] = frozenset(
    {
        IntentClassification.NEW_STRATEGY,
        IntentClassification.EXTEND_STRATEGY,
        IntentClassification.EDIT_STRATEGY,
    }
)

ANSWERING_INTENTS: frozenset[IntentClassification] = frozenset(
    {
        IntentClassification.CLARIFICATION_RESPONSE,
        IntentClassification.SLOT_ANSWER,
        IntentClassification.APPROVAL,
        IntentClassification.DENIAL,
        IntentClassification.EXTEND_STRATEGY,
        IntentClassification.EDIT_STRATEGY,
    }
)
"""The classifications of a message that can answer a question the thread asked.

Any classification in this set, first or later, closes the questions open when
the message arrived, and never one asked later under the same message. A new
request answers none: the questions and this message's answer to them go. Over
a strategy with no step the old request goes too; over steps it stays.
"""


class UserIntent(CamelModel):
    """The Lead's typed parsing of the latest user message.

    The message is the turn's own and is read from the state, so this model
    carries what the classification decides and no text of the message.
    Distinct from ``ProblemFrame``: ``UserIntent`` is per-message and
    re-derived each turn; ``ProblemFrame`` is the durable scoping artifact.
    The Lead writes this via the ``classify_user_intent`` tool as its
    first action on a new user message; the Ledger then derives downstream
    booleans (e.g. ``intent_satisfied``) from typed fields here.
    """

    classification: IntentClassification
    inferred_goal: str = Field(max_length=500)
    is_differential: bool = False
    differential_sides: list[str] = Field(
        default_factory=list,
        max_length=2,
        description=(
            "Two-item list of comparison conditions when "
            "``is_differential`` is True (e.g. ``['asexual', 'gametocyte']``). "
            "Empty otherwise."
        ),
    )
    referenced_step_ids: list[str] = Field(default_factory=list)
    referenced_strategy_ids: list[int] = Field(default_factory=list)
    explicit_constraints: list[Constraint] = Field(
        default_factory=list,
        description=(
            "Typed constraints the user STATED in this message. One of "
            f"{CONSTRAINT_KINDS}. Captured fresh each turn from the literal "
            "message - these are user-explicit by construction and override "
            "scoping's provisional assumptions for the same dimension."
        ),
    )


def _departure_words(request: CombinationRequest, reading: CombinationReading) -> str:
    departures = [
        f'"{c.before}" and "{c.after}" are joined by "{c.text}", which reads as '
        f"{c.operator or 'both operators'}"
        for c in reading.departures(request.operator)
    ]
    if reading.named is not None and reading.named != request.operator:
        departures.append(f"the message names the combination as {reading.named}")
    return "; ".join(departures)


def unstated_operator_refusal(intent: UserIntent, message: str) -> str | None:
    """Why a combination this intent records is not joined the way the message joins it.

    None when every combination whose terms the message carries is joined by
    the researcher's own operator.
    """
    for constraint in intent.explicit_constraints:
        if constraint.kind is not ConstraintKind.COMBINATION:
            continue
        request = CombinationRequest.parse(constraint.requested_value)
        reading = None if request is None else read_combination(message, request)
        if request is None or reading is None or reading.states(request.operator):
            continue
        return (
            f'The combination "{request.expression}" joins its requirements with '
            f"{request.operator}, but the researcher's message does not: "
            f"{_departure_words(request, reading)}. State the operator the "
            "researcher used between those terms, or split the request into "
            'separate constraints. An "or" inside one requirement is an '
            "alternative within it, not a top-level OR."
        )
    return None


def already_classified_message(classification: IntentClassification) -> str:
    """The refusal of a classification that repeats the one this turn holds."""
    return (
        f"This turn is already classified as {classification.value}. Call "
        "classify_user_intent once per turn, and again only to change the "
        "classification; go on with the turn."
    )
