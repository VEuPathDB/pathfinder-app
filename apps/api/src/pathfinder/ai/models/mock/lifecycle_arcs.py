"""Lead arcs that state requirements the thread's lifecycle is derived from: a
narrower organism stated with no withdrawal, and a requirement taken back by
its dimension and value alone."""

from __future__ import annotations

from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.models.mock.arc_readings import intent_of, read_as, stated
from pathfinder.ai.models.mock.calls import lead_final
from pathfinder.ai.models.mock.site_values import SiteValues

# The requirement the withdrawal arc takes back, as the reading states it.
WITHDRAWN_VALUE = "transmembrane domain"

_GOAL = "[mock] change a requirement"
_NARROWED = "The strategy now reads the narrower organism."
_WITHDRAWN = "The transmembrane domain requirement is taken back."


def narrowed_reading(state: PipelineState, words: str) -> UserIntent:
    del words
    organism = SiteValues.for_site(state.site_id).organism
    return intent_of(
        IntentClassification.EDIT_STRATEGY,
        stated("organism", "organism", organism),
        inferredGoal=_GOAL,
    )


withdrawn_reading = read_as(
    IntentClassification.EDIT_STRATEGY,
    inferredGoal=_GOAL,
    withdrawn=[stated("other", "domain", WITHDRAWN_VALUE)],
)


def narrowed_organism(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """The answer to an edit read as stating the site's organism alone."""
    del messages
    return [lead_final(_NARROWED, "await_user")]


def withdrawn_requirement(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """The answer to an edit read as taking one requirement back by its
    dimension and value."""
    del messages
    return [lead_final(_WITHDRAWN, "await_user")]
