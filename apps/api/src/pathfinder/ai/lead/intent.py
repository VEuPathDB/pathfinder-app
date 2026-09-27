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
from pathfinder.domain.strategy.words import words_of


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
"""The classifications of a message that can answer a question the conversation asked.

Any classification in this set, first or later, closes the questions open when
the message arrived, and never one asked later under the same message. A new
request answers none: the questions and this message's answer to them go. Over
a strategy with no step the old request goes too; over steps it stays.
"""


# The classifications that answer something the conversation asked or offered.
_ANSWERS: frozenset[IntentClassification] = frozenset(
    {
        IntentClassification.CLARIFICATION_RESPONSE,
        IntentClassification.SLOT_ANSWER,
        IntentClassification.APPROVAL,
        IntentClassification.DENIAL,
    }
)


class NamedControls(CamelModel):
    """The gene ids a message names as the researcher's positive and negative controls."""

    positive_ids: list[str] = Field(default_factory=list)
    negative_ids: list[str] = Field(default_factory=list)


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
    named_controls: NamedControls | None = Field(
        default=None,
        description=(
            "The gene ids this message names as positive or negative controls, "
            "typed or in an attached gene-ID list, each spelled as the message "
            "spells it. None when the message names no control."
        ),
    )


class ClassifiedIntent(CamelModel):
    """The classification the gate recorded, and one note per correction it made."""

    intent: UserIntent
    corrections: list[str] = Field(default_factory=list)


class RefusedClassification(CamelModel):
    """The last classification the gate refused on this turn, and why."""

    intent: UserIntent
    sentence: str


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


def _occurs_in(gene_id: str, message: str) -> bool:
    """Whether the id's words stand in the message as one consecutive run."""
    wanted = words_of(gene_id)
    held = words_of(message)
    size = len(wanted)
    return size > 0 and any(
        held[k : k + size] == wanted for k in range(len(held) - size + 1)
    )


def unstated_control_ids(named: NamedControls, message: str) -> list[str]:
    """The control ids the intent names that the message does not hold."""
    ids = [*named.positive_ids, *named.negative_ids]
    return [gene_id for gene_id in ids if not _occurs_in(gene_id, message)]


def unstated_controls_message(ids: list[str]) -> str:
    """The refusal of named controls the researcher's message does not hold."""
    return (
        f"The researcher's message does not hold {', '.join(ids)}. Name as "
        "controls only the ids the message types or attaches, spelled as it "
        "spells them."
    )


def nothing_to_answer_message() -> str:
    """The refusal of an answer on a conversation that asked nothing."""
    applies = ", ".join(c.value for c in IntentClassification if c not in _ANSWERS)
    return (
        "No question of yours is open on this conversation and no card waits, "
        "so this message answers none. Classify it as what it asks for: one "
        f"of {applies}."
    )


def repeated_refusal_message(refusal: str) -> str:
    """The failure of a classification that repeats the call just refused."""
    return (
        f"{refusal}\n\nThis call repeats the one just refused, so it fails "
        "without a retry. Ask the researcher the question this refusal states, "
        "through consult_user."
    )


def already_classified_message(classification: IntentClassification) -> str:
    """The refusal of a classification that repeats the one this turn holds."""
    return (
        f"This turn is already classified as {classification.value}. Call "
        "classify_user_intent once per turn, and again only to change the "
        "classification; go on with the turn."
    )
