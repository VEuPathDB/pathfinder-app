from __future__ import annotations

from enum import StrEnum

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field

from pathfinder.domain.caveats import EditDirection
from pathfinder.domain.message_reading import MessageReading, StatedRequest
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
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
    GENE_MODEL_AUDIT = "gene_model_audit"


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

UNRECORDED_INTENTS: frozenset[IntentClassification] = frozenset(
    {IntentClassification.GENE_MODEL_AUDIT}
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
    It is read from the message before the Lead runs; the Ledger then derives
    downstream booleans (e.g. ``intent_satisfied``) from typed fields here.
    """

    classification: IntentClassification
    inferred_goal: str = Field(max_length=500)
    is_differential: bool = False
    differential_sides: list[str] = Field(default_factory=list, max_length=2)
    edit_direction: EditDirection = "other"
    asks_a_change: bool = False
    undo: bool = False
    asks: list[str] = Field(default_factory=list)
    referenced_step_ids: list[str] = Field(default_factory=list)
    explicit_constraints: list[Constraint] = Field(default_factory=list)
    withdrawn_ids: list[str] = Field(default_factory=list)
    named_controls: NamedControls | None = None
    named_gene_ids: list[str] = Field(default_factory=list)
    reading: MessageReading | None = None
    request: StatedRequest | None = None

    def asks_only_to_undo(self) -> bool:
        """Whether the message asks to undo the last change and states no value.

        A combination states a shape and no value, so it is not one. An undo
        withdraws the last change, so a withdrawn requirement keeps it an undo.
        """
        return self.undo and all(
            c.kind is ConstraintKind.COMBINATION for c in self.explicit_constraints
        )


def occurs_in(text: str, message: str) -> bool:
    """Whether the text's words stand in the message as one consecutive run."""
    wanted = words_of(text)
    held = words_of(message)
    size = len(wanted)
    return size > 0 and any(
        held[k : k + size] == wanted for k in range(len(held) - size + 1)
    )


def named_ids(intent: UserIntent) -> list[str]:
    """Every gene id the intent names, controls first."""
    named = intent.named_controls
    controls = [] if named is None else [*named.positive_ids, *named.negative_ids]
    return [*controls, *intent.named_gene_ids]


def untyped_ids(intent: UserIntent, message: str) -> list[str]:
    """The gene ids the intent names that the message text does not hold."""
    return [gene_id for gene_id in named_ids(intent) if not occurs_in(gene_id, message)]
