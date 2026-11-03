"""The intents an arc reads the turn's words as: a fixed one, or one the
request the thread holds decides."""

from __future__ import annotations

from typing import Any

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.models.mock.arc import Reading
from pathfinder.ai.models.mock.site_values import SiteValues


def stated(
    kind: str,
    label: str,
    value: str,
    *,
    hard: bool = True,
    typed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": label,
        "requestedValue": value,
        "quote": value,
        "source": "user_explicit",
        "hard": hard,
        "value": typed,
    }


def intent_of(
    classification: IntentClassification, *requirements: dict[str, Any], **read: Any
) -> UserIntent:
    return UserIntent.model_validate(
        {
            "classification": classification,
            "inferredGoal": f"[mock] {classification.value}",
            **({"explicitConstraints": list(requirements)} if requirements else {}),
            **read,
        }
    )


def read_as(
    classification: IntentClassification, *requirements: dict[str, Any], **read: Any
) -> Reading:
    def reading(state: PipelineState, words: str) -> UserIntent:
        del state, words
        return intent_of(classification, *requirements, **read)

    return reading


def holds_a_request(state: PipelineState) -> bool:
    return state.domain.operational_spec is not None


def build_reading(state: PipelineState, words: str) -> UserIntent:
    del words
    return intent_of(
        IntentClassification.EXTEND_STRATEGY
        if holds_a_request(state)
        else IntentClassification.NEW_STRATEGY
    )


def organism_reading(state: PipelineState, words: str) -> UserIntent:
    organism = SiteValues.for_site(state.site_id).organism
    return intent_of(
        build_reading(state, words).classification,
        stated(
            "organism",
            "organism",
            organism,
            typed={"kind": "organism", "organism": organism},
        ),
    )


def growth_reading(state: PipelineState, words: str) -> UserIntent:
    del words
    return intent_of(
        IntentClassification.EDIT_STRATEGY
        if holds_a_request(state)
        else IntentClassification.NEW_STRATEGY
    )


QUESTION = read_as(IntentClassification.FOLLOW_UP_QUESTION)
NEW_REQUEST = read_as(IntentClassification.NEW_STRATEGY)
EDIT = read_as(IntentClassification.EDIT_STRATEGY)
EXTEND = read_as(IntentClassification.EXTEND_STRATEGY)
