from __future__ import annotations

from enum import StrEnum

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field

from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind


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


# The classifier reads the kinds from the enum, so a new one needs no edit here.
_CONSTRAINT_KINDS = ", ".join(kind.value for kind in ConstraintKind)


class UserIntent(CamelModel):
    """The Lead's typed parsing of the latest user message.

    Distinct from ``ProblemFrame``: ``UserIntent`` is per-message and
    re-derived each turn; ``ProblemFrame`` is the durable scoping artifact.
    The Lead writes this via the ``classify_user_intent`` tool as its
    first action on a new user message; the Ledger then derives downstream
    booleans (e.g. ``intent_satisfied``) from typed fields here.
    """

    raw_text: str
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
            f"{_CONSTRAINT_KINDS}. Captured fresh each turn from the literal "
            "message - these are user-explicit by construction and override "
            "scoping's provisional assumptions for the same dimension."
        ),
    )
